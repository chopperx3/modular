from gui import create_gui
from database import close_connection

if __name__ == "__main__":
    root = create_gui()
    root.mainloop()
    close_connection()