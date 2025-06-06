from pathlib import Path
import subprocess

class FrontendServer:
    def __init__(self, root: Path, port: int = 3000):
        self.root = root
        self.port = str(port)
        self.process = None

    def start(self):
        if not (self.root / 'node_modules').exists():
            subprocess.run(['npm', 'install'], cwd=self.root, check=False)
        subprocess.run(['npx', 'next', 'build'], cwd=self.root, check=False)
        self.process = subprocess.Popen(
            ['npx', 'next', 'start', '-p', self.port],
            cwd=self.root
        )

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
