import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from Adafruit_IO import Client, RequestError
import threading
import time
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class ParkingSystem:
    def __init__(self, root):
        self.root = root
        self.aio = Client("adafruit username", "adafruit io key")
        self.setup_database()
        self.setup_ui()
        threading.Thread(target=self.update_status, daemon=True).start()

    def setup_database(self):
        self.conn = sqlite3.connect('parking_reservations.db')
        self.cursor = self.conn.cursor()
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                status TEXT DEFAULT 'Active',
                reservation_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute("PRAGMA table_info(reservations)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if 'status' not in columns:
            self.cursor.execute('ALTER TABLE reservations ADD COLUMN status TEXT DEFAULT "Active"')
        
        self.conn.commit()

    def setup_ui(self):
        self.root.title("Smart Parking System")
        self.root.geometry("1000x700")
        self.root.configure(bg='#f5f5f5')
        
        # Configure styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Custom styles
        style.configure('Header.TFrame', background='#2c3e50')
        style.configure('Header.TLabel', background='#2c3e50', foreground='white', 
                       font=('Arial', 24, 'bold'))
        style.configure('Slot.TFrame', background='#ecf0f1', relief=tk.GROOVE, borderwidth=2)
        style.configure('Status.TLabel', font=('Arial', 14, 'bold'))
        style.configure('Accent.TButton', foreground='white', background='#3498db',
                       font=('Arial', 12), padding=10)
        style.configure('Footer.TFrame', background='#34495e')
        style.configure('Footer.TLabel', background='#34495e', foreground='#bdc3c7', 
                       font=('Arial', 8))
        style.map('Accent.TButton', 
                 background=[('active', '#2980b9'), ('disabled', '#bdc3c7')])
        
        # Header
        header = ttk.Frame(self.root, style='Header.TFrame', padding=20)
        header.pack(fill=tk.X)
        ttk.Label(header, text="PARKING MANAGEMENT SYSTEM", style='Header.TLabel').pack()
        
        # Control Panel
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Gate Control
        ttk.Label(control_frame, text="Gate Status:", font=('Arial', 12)).pack(side=tk.LEFT)
        self.gate_status = ttk.Label(control_frame, text="Unknown", 
                                   font=('Arial', 12, 'bold'))
        self.gate_status.pack(side=tk.LEFT, padx=10)
        
        open_btn = ttk.Button(control_frame, text="Open Gate", 
                            command=lambda: self.send_gate("Open"),
                            style='Accent.TButton')
        open_btn.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(open_btn, "Open the parking gate")
        
        close_btn = ttk.Button(control_frame, text="Close Gate", 
                             command=lambda: self.send_gate("Closed"),
                             style='Accent.TButton')
        close_btn.pack(side=tk.LEFT)
        self.create_tooltip(close_btn, "Close the parking gate")
        
        # View/Cancel Reservations Button
        manage_btn = ttk.Button(control_frame, text="View/Cancel Reservations", 
                              command=self.manage_reservations,
                              style='Accent.TButton')
        manage_btn.pack(side=tk.RIGHT)
        self.create_tooltip(manage_btn, "View or cancel existing reservations")
        
        # Parking Slots
        slots_frame = ttk.Frame(self.root)
        slots_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.slot_widgets = []
        for i in range(2):
            frame = ttk.Frame(slots_frame, style='Slot.TFrame', padding=15)
            frame.grid(row=0, column=i, padx=10, sticky="nsew")
            
            # Visual slot representation
            canvas = tk.Canvas(frame, width=200, height=200, bg='white', highlightthickness=0)
            canvas.pack(pady=10)
            
            # Draw a car icon placeholder
            canvas.create_rectangle(30, 100, 170, 140, fill='#3498db', outline='')
            canvas.create_oval(40, 140, 80, 180, fill='#2c3e50')
            canvas.create_oval(120, 140, 160, 180, fill='#2c3e50')
            canvas.create_text(100, 50, text=f"SLOT {i+1}", font=('Arial', 16, 'bold'))
            
            # Status Label
            status_label = ttk.Label(frame, text="Loading...", style='Status.TLabel')
            status_label.pack()
            
            # Reserve Button
            btn = ttk.Button(frame, text="RESERVE", 
                           command=lambda i=i: self.reserve_slot(i),
                           style='Accent.TButton')
            btn.pack(fill=tk.X, pady=10)
            
            self.slot_widgets.append({
                'canvas': canvas,
                'label': status_label,
                'button': btn
            })
            
            slots_frame.columnconfigure(i, weight=1)
        
        # Footer (small and subtle)
        footer = ttk.Frame(self.root, style='Footer.TFrame', padding=5)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(footer, text="© 2025 Smart Parking System Designed and Developed By Sasani Lochana & Chaminda Jayasekara", style='Footer.TLabel').pack()

    def create_tooltip(self, widget, text):
        tooltip = tk.Toplevel(widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry("+0+0")
        label = ttk.Label(tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1)
        label.pack()
        
        def enter(event):
            x = widget.winfo_rootx() + widget.winfo_width() + 5
            y = widget.winfo_rooty()
            tooltip.wm_geometry(f"+{x}+{y}")
            tooltip.deiconify()
        
        def leave(event):
            tooltip.withdraw()
        
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)
        tooltip.withdraw()
        return tooltip

    def reserve_slot(self, slot):
        try:
            current_status = self.aio.receive(f'parking.slot{slot+1}').value
            
            if current_status == "Occupied":
                messagebox.showwarning("Occupied", 
                    "This slot is currently in use.\n\nPlease select another slot or wait until it becomes available.")
                return
                
            if current_status == "Reserved":
                self.cancel_reservation_ui(slot+1)
                return
            
            # Create a custom dialog
            dialog = tk.Toplevel(self.root)
            dialog.title(f"Reserve Slot {slot+1}")
            dialog.geometry("400x300")
            dialog.resizable(False, False)
            
            ttk.Label(dialog, text=f"Reserving Slot {slot+1}", 
                     font=('Arial', 14, 'bold')).pack(pady=10)
            
            # Name entry
            ttk.Label(dialog, text="Your Name:").pack(pady=(10,0))
            name_entry = ttk.Entry(dialog, font=('Arial', 12))
            name_entry.pack(pady=5, padx=20, fill=tk.X)
            
            # Email entry
            ttk.Label(dialog, text="Email Address:").pack(pady=(10,0))
            email_entry = ttk.Entry(dialog, font=('Arial', 12))
            email_entry.pack(pady=5, padx=20, fill=tk.X)
            
            # Buttons
            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(pady=20)
            
            def submit():
                name = name_entry.get().strip()
                email = email_entry.get().strip()
                
                if not name or not email:
                    messagebox.showwarning("Missing Information", 
                                        "Please provide both name and email address")
                    return
                    
                if "@" not in email or "." not in email:
                    messagebox.showwarning("Invalid Email", 
                                        "Please enter a valid email address")
                    return
                    
                # Save to database
                self.cursor.execute('''
                    INSERT INTO reservations (slot, name, email, status)
                    VALUES (?, ?, ?, ?)
                ''', (slot+1, name, email, "Active"))
                self.conn.commit()
                
                # Send reservation to ESP32
                self.aio.send('reservations', f"{slot+1}|1|{name}|{email}")
                self.aio.send(f'parking.slot{slot+1}', "Reserved")
                self.send_confirmation_email(slot+1, name, email, "reserved")
                
                messagebox.showinfo("Success", 
                    f"Slot {slot+1} reserved successfully!\n\nConfirmation sent to:\n{email}")
                dialog.destroy()
            
            ttk.Button(btn_frame, text="Confirm Reservation", 
                      command=submit, style='Accent.TButton').pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Cancel", 
                      command=dialog.destroy).pack(side=tk.LEFT)
            
            dialog.grab_set()
            
        except Exception as e:
            messagebox.showerror("Error", f"Reservation failed:\n{str(e)}")

    def cancel_reservation_ui(self, slot):
        try:
            # Find active reservation for this slot
            self.cursor.execute('''
                SELECT id, name, email FROM reservations 
                WHERE slot = ? AND status = 'Active'
            ''', (slot,))
            reservation = self.cursor.fetchone()
            
            if not reservation:
                messagebox.showwarning("Warning", "No active reservation found for this slot!")
                return
                
            res_id, name, email = reservation
            
            # Confirm cancellation
            if not messagebox.askyesno("Confirm Cancellation", 
                                      f"Cancel reservation for Slot {slot}?\n\nName: {name}\nEmail: {email}"):
                return
                
            # Update database
            self.cursor.execute('''
                UPDATE reservations SET status = 'Cancelled' 
                WHERE id = ?
            ''', (res_id,))
            self.conn.commit()
            
            # Send cancellation to ESP32
            self.aio.send('reservations', f"{slot}|0|{name}|{email}")
            self.aio.send(f'parking.slot{slot}', "Free")
            self.send_confirmation_email(slot, name, email, "cancelled")
            
            messagebox.showinfo("Cancelled", "Reservation cancelled successfully!\n\nThe slot is now available.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Cancellation failed:\n{str(e)}")

    def manage_reservations(self):
        try:
            popup = tk.Toplevel(self.root)
            popup.title("Reservation Management")
            popup.geometry("1000x500")
            
            # Treeview widget
            tree = ttk.Treeview(popup, columns=("ID", "Slot", "Name", "Email", "Status", "Time"), 
                              show="headings", selectmode="browse")
            
            # Configure columns
            tree.heading("ID", text="ID")
            tree.heading("Slot", text="Slot")
            tree.heading("Name", text="Name")
            tree.heading("Email", text="Email")
            tree.heading("Status", text="Status")
            tree.heading("Time", text="Reservation Time")
            
            tree.column("ID", width=50, anchor='center')
            tree.column("Slot", width=50, anchor='center')
            tree.column("Name", width=150)
            tree.column("Email", width=200)
            tree.column("Status", width=100)
            tree.column("Time", width=200)
            
            # Add scrollbar
            scrollbar = ttk.Scrollbar(popup, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True, padx=10, pady=10)
            
            # Control buttons frame
            btn_frame = ttk.Frame(popup)
            btn_frame.pack(fill=tk.X, padx=10, pady=5)
            
            # Cancel button
            cancel_btn = ttk.Button(btn_frame, text="Cancel Selected Reservation",
                                 command=lambda: self.cancel_reservation(tree),
                                 style='Accent.TButton')
            cancel_btn.pack(side=tk.LEFT, padx=5)
            self.create_tooltip(cancel_btn, "Cancel the selected reservation")
            
            # Refresh button
            refresh_btn = ttk.Button(btn_frame, text="Refresh",
                                  command=lambda: self.refresh_reservations(tree),
                                  style='Accent.TButton')
            refresh_btn.pack(side=tk.RIGHT)
            self.create_tooltip(refresh_btn, "Refresh the reservation list")
            
            # Load initial data
            self.refresh_reservations(tree)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load reservations:\n{str(e)}")

    def refresh_reservations(self, tree):
        tree.delete(*tree.get_children())
        self.cursor.execute('''
            SELECT id, slot, name, email, status, reservation_time 
            FROM reservations 
            ORDER BY reservation_time DESC
        ''')
        
        for row in self.cursor.fetchall():
            tree.insert("", "end", values=row)

    def cancel_reservation(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a reservation to cancel!")
            return
            
        item = tree.item(selected[0])
        res_id = item['values'][0]
        slot = item['values'][1]
        name = item['values'][2]
        email = item['values'][3]
        
        try:
            if not messagebox.askyesno("Confirm Cancellation", 
                                     f"Cancel reservation for Slot {slot}?\n\nName: {name}\nEmail: {email}"):
                return
                
            self.cursor.execute('''
                UPDATE reservations SET status = 'Cancelled' 
                WHERE id = ?
            ''', (res_id,))
            self.conn.commit()
            
            self.aio.send('reservations', f"{slot}|0|{name}|{email}")
            current_status = self.aio.receive(f'parking.slot{slot}').value
            if current_status == "Reserved":
                self.aio.send(f'parking.slot{slot}', "Free")
            
            self.send_confirmation_email(slot, name, email, "cancelled")
            tree.delete(selected[0])
            messagebox.showinfo("Cancelled", "Reservation cancelled successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Cancellation failed:\n{str(e)}")

    def send_confirmation_email(self, slot, name, email, action):
        try:
            sender_email = "chaminda@gmail.com"
            sender_password = "usampe password"
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
            
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = email
            msg['Subject'] = f"Parking Slot {slot} Reservation {action.capitalize()}"
            
            if action == "reserved":
                body = f"""
                <html>
                  <body>
                    <h2 style="color: #2c3e50;">Parking Reservation Confirmation</h2>
                    <p>Dear {name},</p>
                    <p>Your reservation for <strong>Parking Slot {slot}</strong> has been confirmed.</p>
                    <p>Thank you for using our parking system!</p>
                    <br>
                    <p style="color: #7f8c8d;"><em>This is an automated message - please do not reply</em></p>
                  </body>
                </html>
                """
            else:
                body = f"""
                <html>
                  <body>
                    <h2 style="color: #2c3e50;">Parking Reservation Cancellation</h2>
                    <p>Dear {name},</p>
                    <p>Your reservation for <strong>Parking Slot {slot}</strong> has been cancelled.</p>
                    <p>Thank you for using our parking system!</p>
                    <br>
                    <p style="color: #7f8c8d;"><em>This is an automated message - please do not reply</em></p>
                  </body>
                </html>
                """
            
            msg.attach(MIMEText(body, 'html'))
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
                
        except Exception as e:
            print(f"Failed to send email: {str(e)}")

    def update_status(self):
        color_map = {
            "Occupied": "#e74c3c",
            "Reserved": "#F5CF19",
            "Free": "#2ecc71",
            "Unknown": "#95a5a6"
        }
        
        while True:
            try:
                # Update gate status
                gate_data = self.aio.receive('parking.gate')
                if gate_data:
                    self.root.after(0, lambda status=gate_data.value: self.gate_status.config(
                        text=status,
                        foreground="#2ecc71" if status == "Open" else "#e74c3c"
                    ))
                
                # Update slots
                for i in range(2):
                    data = self.aio.receive(f'parking.slot{i+1}')
                    if data:
                        widget = self.slot_widgets[i]
                        status = data.value
                        color = color_map.get(status, "#95a5a6")
                        
                        # Use a helper function to avoid lambda scoping issues
                        def update_slot(w=widget, s=status, c=color):
                            w['canvas'].delete("all")
                            w['canvas'].create_rectangle(30, 100, 170, 140, fill=c, outline='')
                            w['canvas'].create_oval(40, 140, 80, 180, fill='#2c3e50')
                            w['canvas'].create_oval(120, 140, 160, 180, fill='#2c3e50')
                            w['canvas'].create_text(100, 50, text=f"SLOT {i+1}", font=('Arial', 16, 'bold'))
                            w['canvas'].create_text(100, 80, text=s, font=('Arial', 12))
                            w['label'].config(text=s)
                            w['button'].config(
                                text="CANCEL" if s == "Reserved" else "RESERVE",
                                state="normal" if s != "Occupied" else "disabled"
                            )
                        
                        self.root.after(0, update_slot)
            
            except RequestError:
                pass
            except Exception as e:
                print(f"Update error: {e}")
            
            time.sleep(1)

    def send_gate(self, action):
        try:
            self.aio.send('parking.gate', action)
            messagebox.showinfo("Success", f"Gate command sent: {action}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to control gate:\n{str(e)}")

    def __del__(self):
        self.conn.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = ParkingSystem(root)
    root.mainloop()
