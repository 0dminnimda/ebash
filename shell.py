from __future__ import annotations
from contextlib import ExitStack, contextmanager
from enum import Enum

import shlex
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from subprocess import Popen
from typing import Dict, Generator, Iterable, NamedTuple, TypeVar, overload


class StdinType(Enum):
    NOINPUT = 0
    STDOUT = 1
    STDERR = 2
    PIPE = 3


T1 = TypeVar("T1")
T2 = TypeVar("T2")


Args = Iterable[T1]
Kwargs = Dict[str, T2]


class PopenArgs(NamedTuple):
    stdin: StdinType
    args: Args
    kwargs: Kwargs
    input: str | None = None


@dataclass(repr=False)
class Shell:
    """
    This class works like usual bash/shell and can be used
    as a replacement for them when there's a need to use the power of Python

    Author: 0dminnimda
    """

    _return_code: int = field(default=0, init=False)
    _stdout: str | None = field(default=None, init=False)
    _stderr: str | None = field(default=None, init=False)
    _input: str | None = field(default=None, init=False)
    _args: list[PopenArgs] = field(default_factory=list, init=False)

    def __repr__(self) -> str:
        names = ["return_code", "stdout", "stderr"]
        items = [f"{name}={getattr(self, name)!r}" for name in names]
        return f"{type(self).__name__}({', '.join(items)})"

    @property
    def return_code(self):
        self.execute()
        return self._return_code

    @property
    def stdout(self):
        self.execute()
        return self._stdout

    @property
    def stderr(self):
        self.execute()
        return self._stderr

    @property
    def output(self) -> str:
        return self.stdout or self.stderr or ""

    def __bool__(self) -> bool:
        return self.return_code == 0

    @property
    def failed(self) -> bool:
        return not self

    @property
    def succeeded(self) -> bool:
        return bool(self)

    def execute(self) -> Shell:
        if len(self._args) < 1:
            return self

        for _ in self._inject():
            pass
        return self

    @contextmanager
    def inject(self) -> Generator[Popen, None, None]:
        yield from self._inject()

    def _inject(self) -> Generator[Popen, None, None]:
        if len(self._args) < 1:
            assert False, "No commands were found"

        with ExitStack() as stack:
            stdin, args, kwargs, _ = self._args[0]
            if stdin == StdinType.PIPE:
                kwargs["stdin"] = subprocess.PIPE
            processes = [stack.enter_context(Popen(*args, **kwargs))]

            for stdin, args, kwargs, _ in self._args[1:]:
                if stdin == StdinType.STDOUT:
                    kwargs["stdin"] = processes[-1].stdout
                elif stdin == StdinType.STDERR:
                    kwargs["stdin"] = processes[-1].stderr

                processes.append(stack.enter_context(Popen(*args, **kwargs)))

            if processes[0].stdin:
                processes[0]._stdin_write(  # type: ignore[attr-defined]
                    self._args[0].input
                )
            self._args.clear()
            yield processes[-1]
            self._multiple_communicate(processes)

        if self._stdout and self._stdout.endswith("\n"):
            self._stdout = self._stdout[:-1]

    def _multiple_communicate(self, processes: list[Popen]) -> None:
        try:
            if processes[-1].stdout:
                self._stdout = processes[-1].stdout.read()
                processes[-1].stdout.close()
            elif processes[-1].stderr:
                self._stderr = processes[-1].stderr.read()
                processes[-1].stderr.close()
            processes[-1].wait()
        except:  # noqa # Including KeyboardInterrupt, communicate handled that.
            for process in processes:
                process.kill()
                # We don't call process.wait() as .__exit__ does that for us.
            raise
        self._return_code = processes[-1].poll() or 0

    def _communicate(
        self, process: Popen, input: str | None = None, timeout=None
    ) -> None:
        # uses cpython implementation of subprocess.run
        # noqa # SEE: https://github.com/python/cpython/blob/faf8068dd01c8eee7f6ea3f9e608126bf2034dc1/Lib/subprocess.py#L506
        try:
            self._stdout, self._stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            if subprocess._mswindows:  # type: ignore[attr-defined]
                # Windows accumulates the output in a single blocking
                # read() call run on child threads, with the timeout
                # being done in a join() on those threads.  communicate()
                # _after_ kill() is required to collect that and add it
                # to the exception.
                exc.stdout, exc.stderr = process.communicate()
            else:
                # POSIX _communicate already populated the output so
                # far into the TimeoutExpired exception.
                process.wait()
            raise
        except:  # noqa # Including KeyboardInterrupt, communicate handled that.
            process.kill()
            # We don't call process.wait() as .__exit__ does that for us.
            raise
        self._return_code = process.poll() or 0

    def _add_args(
        self,
        command: str,
        stderr_to_stdout: bool = False,
        stderr_as_stdin: bool = False,
        fallback_stdout: int | None = None,
        fallback_stderr: int | None = None,
    ) -> PopenArgs:
        stdin = StdinType.NOINPUT
        if self._args:
            prev_stdout = self._args[-1].kwargs.get("stdout")
            prev_stderr = self._args[-1].kwargs.get("stderr")

            if prev_stderr in (subprocess.PIPE, None) and stderr_as_stdin:
                self._args[-1].kwargs["stderr"] = subprocess.PIPE
                stdin = StdinType.STDERR
            elif prev_stderr == subprocess.STDOUT or prev_stdout == subprocess.PIPE:
                stdin = StdinType.STDOUT
        elif self._input is not None:
            stdin = StdinType.PIPE

        kwargs: Kwargs = dict(
            stdout=fallback_stdout,
            stderr=subprocess.STDOUT if stderr_to_stdout else fallback_stderr,
            stdin=None,
            encoding="utf-8",
            text=True,
        )
        args = PopenArgs(stdin, (shlex.split(command),), kwargs, self._input)
        self._input = None
        self._args.append(args)
        return args

    def run(self, command: str, stderr_to_stdout: bool = False) -> Shell:
        self._add_args(command, stderr_to_stdout=stderr_to_stdout)
        return self.execute()

    def pipe(
        self,
        command: str,
        stderr_to_stdout: bool = False,
        stderr_as_stdin: bool = False,
    ) -> Shell:
        self._add_args(
            command,
            fallback_stdout=subprocess.PIPE,
            fallback_stderr=subprocess.PIPE,
            stderr_to_stdout=stderr_to_stdout,
            stderr_as_stdin=stderr_as_stdin,
        )
        return self

    def input(self, data: str) -> Shell:
        if self._args:
            assert (
                False
            ), "Are you really trying to add an input in the middle of the pipe?"
        self._input = data
        return self

    @staticmethod
    def argv(index: int) -> str:
        if index >= len(sys.argv):
            return ""
        return sys.argv[index]


@dataclass
class FancyShell(Shell):
    def fancy_reset(self) -> FancyShell:
        return self

    @overload
    def __or__(self, other: str) -> FancyShell:
        ...

    @overload
    def __or__(self, other: FancyShell) -> str:
        ...

    def __or__(self, other):
        if isinstance(other, str):
            # one of the pipes
            self.pipe(other)
            return self
        if isinstance(other, type(self)):
            # everything is done, clean up if the last was a pipe
            self.fancy_reset()
            return self.output
        return NotImplemented

    def __matmul__(self, other: str) -> FancyShell:
        # the last one
        self.run(other)
        return self.fancy_reset()

    def __rmatmul__(self, other: str) -> FancyShell:
        # the last one
        self.run(other)
        return self.fancy_reset()

    def __rrshift__(self, other: str) -> FancyShell:
        self.input(other)
        return self


if __name__ == "__main__":
    fs = FancyShell()
    shell = Shell()
    print(shell)
    exe = sys.executable

    # echo "Hello world!"
    shell.run('echo "Hello world!"')
    fs | 'echo "Hello world!"' @ fs
    fs @ 'echo "Hello world!"'

    # echo "SoMe WeIrd DaTa" | sha256sum
    shell.pipe('echo "SoMe WeIrd DaTa"').run("sha256sum")
    fs | 'echo "Hello world!"' | "sha256sum" @ fs

    # sha256sum <<< "SoMe WeIrd DaTa"
    shell.input("SoMe WeIrd DaTa").run("sha256sum")
    "SoMe WeIrd DaTa" >> fs | "sha256sum" @ fs
    ("SoMe WeIrd DaTa" >> fs) @ "sha256sum"  # if you use input + direct run you need prentices

    # DATA_HASH=$(echo "SoMe WeIrd DaTa" | sha256sum)
    # or DATA_HASH=$(sha256sum <<< "SoMe WeIrd DaTa")
    data_hash = shell.input("SoMe WeIrd DaTa").pipe("sha256sum").output
    data_hash2 = "SoMe WeIrd DaTa" >> fs | "sha256sum" | fs

    # echo "Hash - $DATA_HASH"
    print(f"Hash - {data_hash}")
    print(f"Hash - {data_hash2}")

    # false || echo "It failed"
    shell.run("false") or print("It failed")
    fs @ ("false") or print("It failed")

    # true && echo "So true!"
    shell.run("true") and print("So true!")
    fs @ "true" and print("So true!")

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
        print("Running!")
        shell.run(f"'{exe}' {shell.argv(0)} argument")
        print(f"Result - {shell.return_code}")

    # do_something_that_takes_a_lot_of_time & do_other_thing
    # parallel execution is currently not implemented

    # (cd somewhere/else)
    # spawning subshells is also not implemented

    generator = """
import time
for i in range(5):
    print(f'Hi-{i}, sent {time.time()}')
    time.sleep(0.5)
    """

    echoer = """
import sys
import time
for _ in range(5):
    print(f'Echoer-{sys.argv[1]} got {input()!r} at {time.time()}')
    """

    # no buffering while piping fow arbitrary number of pipes
    # python3.9 -u -c "$GENERATOR" | python3.9 -c "$ECHOER" 1
    shell.pipe(f'{exe} -u -c "{generator}"').run(f'{exe} -c "{echoer}" 1')
    fs | f'{exe} -u -c "{generator}"' | f'{exe} -c "{echoer}" 1' @ fs

    # python3.9 -u -c "$GENERATOR" | python3.9 -c "$ECHOER" 1 | python3.9 -c "$ECHOER" 2
    shell.pipe(f'{exe} -u -c "{generator}"').pipe(f'{exe} -c "{echoer}" 1').run(f'{exe} -c "{echoer}" 2')  # fmt: skip
    fs | f'{exe} -u -c "{generator}"' | f'{exe} -c "{echoer}" 1' | f'{exe} -c "{echoer}" 2' @ fs

    # read from the stdout by character
    # (I don't want to think about how to implement it in bash)
    shell.pipe(f'{exe} -u -c "{generator}"')
    with shell.inject() as process:
        while r := process.stdout.read(1):
            print(end=" " + r)
        print("End!")
    fs | f'{exe} -u -c "{generator}"'
    with fs.inject() as process:
        while r := process.stdout.read(1):
            print(end=" " + r)
        print("End!")

    std_out_n_err = """
import sys
print('Err', file=sys.stderr)
print('Out')
    """

    # python3 -c "$STD_OUT_N_ERR" 2>&1
    shell.run(f'{exe} -c "{std_out_n_err}"', stderr_to_stdout=True)
    # currently now possible with fancy shell syntax
    fs.run(f'{exe} -c "{std_out_n_err}"', stderr_to_stdout=True)

    # UPD: Add a fancy syntactic shell class
