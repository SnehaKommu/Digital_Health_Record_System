import mysql.connector

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Aishu@123",  # your mysql password
        database="health_db"
    )