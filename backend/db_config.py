import mysql.connector

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Sneha@3684",  # your mysql password
        database="health_db"
    )