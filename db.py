
import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load database configuration from .env
load_dotenv()


class Database:

    def __init__(self):
        self.db = None

    def connect(self):
        """Establish a connection to the MySQL database."""
        try:
            self.db = mysql.connector.connect(
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT", 3306)),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME")
            )

            if self.db.is_connected():
                print("Successfully connected to MySQL!")
                return True

        except Error as e:
            print("Database connection error:", e)
            self.db = None

        return False

    def close(self):
        """Close the database connection."""
        if self.db and self.db.is_connected():
            self.db.close()
            print("Database connection closed.")


# Test the connection when this file is executed directly
if __name__ == "__main__":
    database = Database()

    if database.connect():
        database.close()
