from locust import HttpUser, task, between
import json
import random


class DentalAIUser(HttpUser):
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        response = self.client.post("/api/auth/login", json={
            "email": "admin@example.com",
            "password": "admin123456"
        })
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")

    def get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @task(10)
    def chat_query(self):
        questions = [
            "What is the treatment for dental caries?",
            "How to manage toothache?",
            "What are the signs of gum disease?",
            "Explain root canal procedure",
            "What causes tooth sensitivity?",
            "How to prevent cavities?",
            "What is periodontitis?",
            "Treatment for broken tooth",
            "What are dental implants?",
            "How does teeth whitening work?",
        ]
        self.client.post("/api/chat", json={
            "question": random.choice(questions),
        }, headers=self.get_headers())

    @task(5)
    def chat_stream(self):
        self.client.post("/api/chat/stream", json={
            "question": "What is the best treatment for gum disease?",
        }, headers=self.get_headers())

    @task(3)
    def list_sessions(self):
        self.client.get("/api/chat/sessions", headers=self.get_headers())

    @task(2)
    def get_documents(self):
        self.client.get("/api/admin/documents", headers=self.get_headers())

    @task(1)
    def health_check(self):
        self.client.get("/api/health")

    @task(1)
    def get_disclaimer(self):
        self.client.get("/api/disclaimer")


class AdminUser(HttpUser):
    wait_time = between(2, 5)
    token = None
    weight = 1

    def on_start(self):
        response = self.client.post("/api/auth/login", json={
            "email": "admin@example.com",
            "password": "admin123456"
        })
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")

    def get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @task(5)
    def admin_list_documents(self):
        self.client.get("/api/admin/documents", headers=self.get_headers())

    @task(3)
    def admin_dataset_status(self):
        self.client.get("/api/admin/dataset/status", headers=self.get_headers())

    @task(2)
    def admin_ingestion_logs(self):
        self.client.get("/api/admin/documents", headers=self.get_headers())
