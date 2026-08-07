import os
import sys
import subprocess
import threading
import time

def run_command(command, cwd=None, env=None):
    """Runs a shell command and streams the output."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True,
        text=True,
        bufsize=1,
        env=env
    )
    
    # Stream output
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
    
    process.stdout.close()
    return process.wait()

def start_backend():
    print("[RUNNER] Starting FastAPI Backend on http://localhost:8000...")
    # Find Python executable (support virtual environment if present)
    venv_python = os.path.abspath(os.path.join("backend", ".venv", "Scripts", "python.exe")) if os.name == 'nt' else os.path.abspath(os.path.join("backend", ".venv", "bin", "python"))
    python_cmd = venv_python if os.path.exists(venv_python) else sys.executable
    
    # Run uvicorn reload
    cmd = f'"{python_cmd}" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload'
    run_command(cmd, cwd="backend")

def start_frontend():
    print("[RUNNER] Starting Next.js Frontend on http://localhost:3000...")
    cmd = "npm run dev"
    run_command(cmd, cwd="frontend")

def setup_backend():
    print("[RUNNER] Checking backend virtual environment...")
    backend_dir = "backend"
    venv_dir = os.path.abspath(os.path.join(backend_dir, ".venv"))
    
    if not os.path.exists(venv_dir):
        print("[RUNNER] Creating Python virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", venv_dir], cwd=backend_dir)
        
    venv_python = os.path.abspath(os.path.join(venv_dir, "Scripts", "python.exe")) if os.name == 'nt' else os.path.abspath(os.path.join(venv_dir, "bin", "python"))
    venv_pip = os.path.abspath(os.path.join(venv_dir, "Scripts", "pip.exe")) if os.name == 'nt' else os.path.abspath(os.path.join(venv_dir, "bin", "pip"))
    
    print("[RUNNER] Installing Python dependencies...")
    subprocess.run([venv_pip, "install", "-r", "requirements.txt"], cwd=backend_dir)

def setup_frontend():
    print("[RUNNER] Checking frontend dependencies...")
    frontend_dir = "frontend"
    node_modules = os.path.join(frontend_dir, "node_modules")
    
    if not os.path.exists(node_modules):
        print("[RUNNER] Installing npm packages (this may take a minute)...")
        subprocess.run("npm install", shell=True, cwd=frontend_dir)

def main():
    # Setup step
    setup_backend()
    
    # Initialize frontend folders first if not already bootstrapped by Next.js
    if not os.path.exists("frontend/package.json"):
        print("[RUNNER] Frontend Next.js folder not initialized yet. Run Next.js setup first.")
        # We will create frontend next.js files shortly
        return
        
    setup_frontend()
    
    # Spawn servers
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    
    backend_thread.start()
    frontend_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[RUNNER] Shutting down servers. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
