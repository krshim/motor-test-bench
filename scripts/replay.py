import time
import pandas as pd
import numpy as np
from pyulog import ULog
from pymavlink import mavutil
import sys

# ==========================================
# ⚙️ 설정 (여기를 수정하세요)
# ==========================================
LOG_FILE = 'test_log.ulg'  # 가지고 있는 ulog 파일명
TARGET_MOTOR_IDX = 0                # 로그에서 가져올 모터 번호 (0부터 시작, 0=Motor1, 1=Motor2...)
BENCH_MOTOR_ID = 1                  # 테스트 벤치에서 실제로 돌릴 모터 번호 (1부터 시작)
PIXHAWK_PORT = '/dev/ttyACM0'               # 픽스호크 포트 (윈도우: COMx, 리눅스: /dev/ttyACM0)
BAUD_RATE = 57600
PLAYBACK_SPEED = 1.0                # 재생 속도 (1.0 = 정배속, 0.5 = 절반 속도)
MAX_THROTTLE_LIMIT = 0.8            # 안전장치: 최대 출력 제한 (0.0 ~ 1.0)
# ==========================================

def parse_ulog(filename):
    print(f"📂 로그 파일 로딩 중: {filename}...")
    try:
        ulog = ULog(filename)

        # 'actuator_outputs' 토픽에서 데이터 추출 (모터 PWM 신호)
        # 보통 actuator_outputs_0 이 메인 모터입니다.
        data = ulog.get_dataset('actuator_outputs')
        df = pd.DataFrame(data.data)

        # 타임스탬프 (마이크로초 -> 초 변환 및 0부터 시작하도록 조정)
        df['timestamp'] = (df['timestamp'] - df['timestamp'].iloc[0]) / 1e6

        # 모터 데이터 추출 (output[0], output[1]... 형식으로 되어 있음)
        # PX4 로그는 보통 1000~2000(PWM) 또는 0~1(Normalized)로 저장됨
        # 여기서는 데이터를 확인하고 0.0~1.0 사이로 정규화가 필요할 수 있음

        motor_col = f'output[{TARGET_MOTOR_IDX}]'
        if motor_col not in df.columns:
            print(f"❌ 오류: 로그에 모터 {TARGET_MOTOR_IDX}번 데이터가 없습니다.")
            print(f"가능한 컬럼: {df.columns}")
            sys.exit(1)

        print(f"✅ 데이터 추출 완료! 총 {len(df)}개 포인트")
        return df[['timestamp', motor_col]]

    except Exception as e:
        print(f"❌ 로그 파싱 실패: {e}")
        sys.exit(1)

def connect_pixhawk():
    print(f"🔌 픽스호크 연결 중 ({PIXHAWK_PORT})...")
    conn = mavutil.mavlink_connection(PIXHAWK_PORT, baud=BAUD_RATE)
    conn.wait_heartbeat()
    print("✅ 픽스호크 연결 성공!")
    return conn

def send_motor_command(conn, throttle):
    # 안전 제한 적용
    if throttle > MAX_THROTTLE_LIMIT:
        throttle = MAX_THROTTLE_LIMIT
    if throttle < 0:
        throttle = 0

    # MAVLink로 모터 테스트 명령 전송
    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0,
        BENCH_MOTOR_ID, # 제어할 모터 번호
        0,              # Throttle type (0=Percent)
        throttle,       # Throttle value (0.0 ~ 1.0)
        0.5,            # Timeout (0.5초 동안 명령 없으면 멈춤)
        1, 0, 0
    )

def run_replay(conn, df, motor_col_name):
    print("\n🚀 3초 뒤 모터 리플레이를 시작합니다! (주의하세요)")
    time.sleep(3)

    start_time = time.time()
    log_start_time = df['timestamp'].iloc[0]

    # 데이터 순회
    for index, row in df.iterrows():
        current_log_time = row['timestamp']
        target_pwm_raw = row[motor_col_name]

        # 데이터 정규화 (로그 값이 1000~2000인 경우 0.0~1.0으로 변환)
        # 만약 로그가 이미 0~1 사이라면 이 부분 수정 필요
        if target_pwm_raw > 100:
            throttle = (target_pwm_raw - 1000) / 1000.0
        else:
            throttle = target_pwm_raw

        # 재생 속도 동기화 (Sleep)
        elapsed_real_time = (time.time() - start_time) * PLAYBACK_SPEED
        time_diff = current_log_time - elapsed_real_time

        if time_diff > 0:
            time.sleep(time_diff)

        # 명령 전송
        send_motor_command(conn, throttle)

        # 상태 출력 (10번에 한번만 출력해서 속도 저하 방지)
        if index % 10 == 0:
            print(f"⏱ Time: {current_log_time:.2f}s | Output: {throttle*100:.1f}%", end='\r')

    print("\n🏁 리플레이 종료. 모터를 정지합니다.")
    send_motor_command(conn, 0)

# === 실행 ===
if __name__ == "__main__":
    motor_col = f'output[{TARGET_MOTOR_IDX}]'

    # 1. 로그 데이터 준비
    df_motor = parse_ulog(LOG_FILE)

    # 2. 픽스호크 연결
    px4 = connect_pixhawk()

    # 3. 리플레이 시작
    try:
        run_replay(px4, df_motor, motor_col)
    except KeyboardInterrupt:
        print("\n🛑 비상 정지!")
        send_motor_command(px4, 0)
