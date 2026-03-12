@router.post("/tasks/create")
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = Task(
        prompt=payload.prompt,
        task_type=payload.task_type,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "status": "pending"}

