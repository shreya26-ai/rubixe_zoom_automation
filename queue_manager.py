from collections import deque

speaking_queue = deque()

def add_participant(name):
    speaking_queue.append(name)

def remove_participant(name):
    if name in speaking_queue:
        speaking_queue.remove(name)

def get_queue():
    return list(speaking_queue)
