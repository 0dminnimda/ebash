from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass


@dataclass
class Shell:
    """
    This class works like usual bash/shell and can be used
    as a replacement for them when there's a need to use the power of Python

    Author: 0dminnimda
    """

    return_code: int = 0
    stdout: str | None = None
    stderr: str | None = None

    def update(
        self, return_code: int = 0, stdout: str | None = None, stderr: str | None = None
    ) -> Shell:
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        return self

    @property
    def output(self) -> str:
        return self.stdout or self.stderr or ""

    def run(self, command: str, use_stdout: bool = True) -> Shell:
        completed = subprocess.run(
            shlex.split(command),
            input=self.output,
            capture_output=not use_stdout,
            encoding="utf-8",
            text=True,
            # shell=True,
        )
        return self.update(completed.returncode, completed.stdout, completed.stderr)

    def pipe(self, command: str) -> Shell:
        return self.run(command, use_stdout=False)

    def input(self, data: str) -> Shell:
        return self.update(stdout=data)


shell = Shell()

# echo "Hello world!"
shell.run('echo "Hello world!"')

# echo "SoMe WeIrd DaTa" | sha256sum
shell.pipe('echo "SoMe WeIrd DaTa"').run("sha256sum")

# sha256sum <<< "SoMe WeIrd DaTa"
shell.input('SoMe WeIrd DaTa').run("sha256sum")

# DATA_HASH=$(echo "SoMe WeIrd DaTa" | sha256sum)
data_hash = shell.input('SoMe WeIrd DaTa').pipe("sha256sum").output

# do_something_that_takes_a_lot_of_time & do_other_thing
# parallel execution is currently not implemented
