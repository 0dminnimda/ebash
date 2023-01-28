from __future__ import annotations

import sys
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

    def __bool__(self) -> bool:
        return self.return_code == 0

    @property
    def failed(self) -> bool:
        return not self

    @property
    def succeeded(self) -> bool:
        return bool(self)

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
        if completed.stdout and completed.stdout.endswith("\n"):
            completed.stdout = completed.stdout[:-1]
        return self.update(completed.returncode, completed.stdout, completed.stderr)

    def pipe(self, command: str) -> Shell:
        return self.run(command, use_stdout=False)

    def input(self, data: str) -> Shell:
        return self.update(stdout=data)

    @staticmethod
    def argv(index: int) -> str:
        if index >= len(sys.argv):
            return ""
        return sys.argv[index]


if __name__ == "__main__":
    shell = Shell()

    # echo "Hello world!"
    shell.run('echo "Hello world!"')

    # echo "SoMe WeIrd DaTa" | sha256sum
    shell.pipe('echo "SoMe WeIrd DaTa"').run("sha256sum")

    # sha256sum <<< "SoMe WeIrd DaTa"
    shell.input("SoMe WeIrd DaTa").run("sha256sum")

    # DATA_HASH=$(echo "SoMe WeIrd DaTa" | sha256sum)
    # or DATA_HASH=$(sha256sum <<< "SoMe WeIrd DaTa")
    data_hash = shell.input("SoMe WeIrd DaTa").pipe("sha256sum").output

    # echo "Hash - $DATA_HASH"
    print(f"Hash - {data_hash}")

    # false || echo "It failed"
    shell.run("false") or print("It failed")

    # true && echo "So true!"
    shell.run("true") and print("So true!")

    # false; echo $?
    print(shell.run("false").return_code)

    # if [[ $1 ]]; then
    #     exit 2
    # else
    #     echo "Running!"
    #     $0 argument
    #     echo "Result - $?"
    # fi
    if shell.argv(1):
        exit(2)
    else:
        print('Running!')
        shell.run(f"'{sys.executable}' {shell.argv(0)} argument")
        print(f"Result - {shell.return_code}")

    # do_something_that_takes_a_lot_of_time & do_other_thing
    # parallel execution is currently not implemented

    # (cd somewhere/else)
    # spawning subshells is also not implemented
