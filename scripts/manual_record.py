import tkinter as tk
from tkinter import ttk
import serial
from pymavlink import mavutil
import csv
import time
from datetime import datetime

# ==========================================
# ⚙️ SETTINGS
# ==========================================
PIXHAWK_PORT = '/dev/ttyACM0'
LOADCELL_PORT = ''  # 로드셀 없으면 비워두기: ''
BAUD_RATE = 57600
MOTOR_ID = 1
# ==========================================

class MotorTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Motor Test Bench (Recorder)")
        self.root.geometry("500x550")

        self.px4 = None
        self.loadcell = None
        self.is_recording = False
        self.csv_file = None
        self.csv_writer = None
        self.start_time = 0

        self.create_widgets()
        self.connect_hardware()
        self.update_data()

    def create_widgets(self):
        style = ttk.Style()
        style.configure("Big.TLabel", font=("Arial", 20, "bold"))

        # Title
        ttk.Label(self.root, text="Motor Manual Control & Record", font=("Arial", 16)).pack(pady=10)

        # Data Frame
        self.frame_data = ttk.Frame(self.root)
        self.frame_data.pack(pady=10)

        # Thrust
        self.lbl_thrust = ttk.Label(self.frame_data, text="0 g", style="Big.TLabel", foreground="blue")
        self.lbl_thrust.grid(row=0, column=0, columnspan=2, pady=10)
        ttk.Label(self.frame_data, text="Thrust").grid(row=1, column=0, columnspan=2)

        # Volt / Current
        self.lbl_volt = ttk.Label(self.frame_data, text="0.0 V", font=("Arial", 12))
        self.lbl_volt.grid(row=2, column=0, padx=20, pady=10)
        ttk.Label(self.frame_data, text="Voltage").grid(row=3, column=0)

        self.lbl_curr = ttk.Label(self.frame_data, text="0.0 A", font=("Arial", 12))
        self.lbl_curr.grid(row=2, column=1, padx=20, pady=10)
        ttk.Label(self.frame_data, text="Current").grid(row=3, column=1)

        # Slider
        self.frame_control = ttk.LabelFrame(self.root, text=" Throttle Control ")
        self.frame_control.pack(fill="x", padx=20, pady=20)

        self.slider_val = tk.DoubleVar()
        self.slider = ttk.Scale(self.frame_control, from_=0, to=100, orient='horizontal',
                                command=self.on_slider_change, variable=self.slider_val)
        self.slider.pack(fill="x", padx=10, pady=10)
        self.lbl_throttle = ttk.Label(self.frame_control, text="Output: 0.0 %", font=("Arial", 12, "bold"))
        self.lbl_throttle.pack()

        # [REC] Button (Emoji Removed)
        self.btn_record = tk.Button(self.root, text="[REC] Start Recording",
                                    bg="lightgray", font=("Arial", 12, "bold"),
                                    command=self.toggle_recording)
        self.btn_record.pack(fill="x", padx=20, pady=5)

        # Emergency Button
        self.btn_stop = tk.Button(self.root, text="EMERGENCY STOP (Space)",
                                  bg="red", fg="white", font=("Arial", 14, "bold"),
                                  command=self.emergency_stop)
        self.btn_stop.pack(fill="x", padx=20, pady=10)

        self.root.bind('<space>', lambda e: self.emergency_stop())

    def connect_hardware(self):
        try:
            self.px4 = mavutil.mavlink_connection(PIXHAWK_PORT, baud=BAUD_RATE)
            self.px4.wait_heartbeat()
            print("Pixhawk Connected!")
        except:
            print("Pixhawk Connection Failed")

        if LOADCELL_PORT != '':
            try:
                self.loadcell = serial.Serial(LOADCELL_PORT, 9600, timeout=0.1)
            except:
                print("LoadCell Connection Failed")

    def toggle_recording(self):
        if not self.is_recording:
            # Start Recording
            self.is_recording = True
            filename = f"TestLog_{datetime.now().strftime('%H%M%S')}.csv"
            self.csv_file = open(filename, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["Time(s)", "Throttle(%)", "Voltage(V)", "Current(A)", "Thrust(g)", "Power(W)"])

            self.start_time = time.time()
            # Changed text to simple English
            self.btn_record.config(text="[STOP] RECORDING...", bg="pink", fg="red")
            print(f"Recording started: {filename}")
        else:
            # Stop Recording
            self.is_recording = False
            if self.csv_file:
                self.csv_file.close()
            self.btn_record.config(text="[REC] Start Recording", bg="lightgray", fg="black")
            print("Recording saved!")

    def on_slider_change(self, event):
        val = self.slider_val.get()
        self.lbl_throttle.config(text=f"Output: {val:.1f} %")
        if self.px4:
            self.px4.mav.command_long_send(
                self.px4.target_system, self.px4.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0,
                MOTOR_ID, 0, val/100.0, 2, 1, 0, 0
            )

    def emergency_stop(self):
        self.slider.set(0)
        self.on_slider_change(None)
        if self.is_recording:
            self.toggle_recording() # Stop recording if active
        print("EMERGENCY STOP!")

    def update_data(self):
        volt, curr, thrust = 0.0, 0.0, 0

        # Read Pixhawk
        if self.px4:
            msg = self.px4.recv_match(type='BATTERY_STATUS', blocking=False)
            if msg:
                volt = msg.voltages[0] / 1000.0
                curr = msg.current_battery / 100.0
                self.lbl_volt.config(text=f"{volt:.1f} V")
                self.lbl_curr.config(text=f"{curr:.1f} A")

        # Read LoadCell
        if self.loadcell and self.loadcell.in_waiting:
            try:
                thrust = float(self.loadcell.readline().decode().strip())
                self.lbl_thrust.config(text=f"{thrust:.0f} g")
            except: pass

        # Save to CSV if recording
        if self.is_recording:
            elapsed = time.time() - self.start_time
            throttle = self.slider_val.get()
            power = volt * curr
            self.csv_writer.writerow([f"{elapsed:.2f}", throttle, volt, curr, thrust, f"{power:.1f}"])

        self.root.after(100, self.update_data)

if __name__ == "__main__":
    root = tk.Tk()
    app = MotorTesterApp(root)
    root.mainloop()
