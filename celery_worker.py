#!/usr/bin/env python
"""Celery worker entry point."""
import os
import sys
from app import create_app

# Create Flask app with Celery initialization
app = create_app(os.getenv("FLASK_ENV", "development"), init_celery_app=True)

if __name__ == "__main__":
    from app.tasks import celery
    
    # Get queue and concurrency from command line args
    queue = sys.argv[1] if len(sys.argv) > 1 else "default"
    concurrency = sys.argv[2] if len(sys.argv) > 2 else "4"
    
    # Start the Celery worker
    from app.tasks import celery
    # Explicit node name: containers on host networking share the machine's
    # hostname, and duplicate Celery nodenames break monitoring/control.
    celery.worker_main([
        'worker',
        '-n', f'brainstormer-{queue}@%h',
        '-Q', queue,
        '-c', concurrency,
        '--loglevel=info'
    ])