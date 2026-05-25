import tkinter as tk
from gui.trajectory_window import TrajectoryWindow

if __name__ == "__main__":
    root = tk.Tk()
    app = TrajectoryWindow(root)
    root.mainloop()