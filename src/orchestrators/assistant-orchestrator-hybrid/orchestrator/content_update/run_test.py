from celery_test.tasks import dummy_task

if __name__ == "__main__":
    result = dummy_task.delay(2, 3)
    print("Task sent:", result.id)
    print("Result:", result.get(timeout=10))
