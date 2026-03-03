import os
import subprocess

class BuildTool:
    def __init__(self, project_path, configuration="Debug"):
        self.project_path = os.path.abspath(project_path)
        self.configuration = configuration
        self.solution_file = self._detect_solution_file()

        if not self.solution_file:
            print("Scanning directory:", self.project_path)
            print("Files found:", os.listdir(self.project_path))
            raise FileNotFoundError("No .sln or .slnx file found in the project root.")

    def _detect_solution_file(self):
        for file in os.listdir(self.project_path):
            if file.lower().endswith((".sln", ".slnx")):
                return file
        return None

    def run_build(self):
        command = [
            "msbuild",
            self.solution_file,
            "/t:Build",
            "/v:minimal"
        ]

        process = subprocess.run(
            command,
            cwd = self.project_path,
            capture_output= True,
            text = True
        )

        return {
            "exit_code" : process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr
        }