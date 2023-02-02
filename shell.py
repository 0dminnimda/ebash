from __future__ import annotations

import shlex
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from subprocess import Popen
from typing import Dict, Iterable, Iterator, NamedTuple, TypeVar, overload


class StdinType(Enum):
    NOINPUT = 0
    STDOUT = 1
    STDERR = 2
    PIPE = 3


T1 = TypeVar("T1")
T2 = TypeVar("T2")


Args = Iterable[T1]
Kwargs = Dict[str, T2]


@dataclass
class PopenArgs:
    stdin: StdinType
    args: Args
    kwargs: Kwargs
    input: str | None = None


@dataclass
class Executor(ExitStack):
    return_code: int = field(default=0, init=False)
    stdout: str | None = field(default=None, init=False)
    stderr: str | None = field(default=None, init=False)
    _processes: list[Popen] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__init__()

    def reset(self) -> None:
        if len(self._processes) != 0:
            self.close()
        self.return_code = 0
        self.stdout = None
        self.stderr = None
        self._processes = []

    def execute(
        self, params_list: list[PopenArgs], input: str | None = None
    ) -> Executor:
        if len(params_list) == 0:
            raise ValueError(
                "No parameters were found, you should supply at least one parameter"
            )

        self.reset()
        processes = self._processes

        params0 = params_list[0]
        if params0.stdin == StdinType.PIPE:
            params0.kwargs["stdin"] = subprocess.PIPE
        processes.append(self.enter_context(Popen(*params0.args, **params0.kwargs)))

        for params in params_list[1:]:
            if params.stdin == StdinType.STDOUT:
                params.kwargs["stdin"] = processes[-1].stdout
            elif params.stdin == StdinType.STDERR:
                params.kwargs["stdin"] = processes[-1].stderr

            processes.append(self.enter_context(Popen(*params.args, **params.kwargs)))

        if processes[0].stdin:
            processes[0]._stdin_write(params0.input)  # type: ignore[attr-defined]
        return self

    __call__ = execute

    def __enter__(self):
        return super().__enter__()

    def __exit__(self, *exc_details):
        try:
            if self._processes[-1].stdout:
                self.stdout = self._processes[-1].stdout.read()
                self._processes[-1].stdout.close()
            elif self._processes[-1].stderr:
                self.stderr = self._processes[-1].stderr.read()
                self._processes[-1].stderr.close()
            self._processes[-1].wait()
        except:  # noqa # Including KeyboardInterrupt, communicate handled that.
            for process in self._processes:
                process.kill()
                # We don't call process.wait() as .__exit__ does that for us.
            raise

        self.return_code = self._processes[-1].poll() or 0

        # XXX: should this condition be here?
        # should executor also try to imitate shell and not just wrap subprocess?
        if self.stdout and self.stdout.endswith("\n"):
            self.stdout = self.stdout[:-1]

        self._processes.clear()
        return super().__exit__(*exc_details)

    def close(self) -> None:
        super().close()


@dataclass(repr=False)
class Shell:
    """
    This class works like usual bash/shell and can be used
    as a replacement for them when there's a need to use the power of Python

    Author: 0dminnimda
    """

    _executor: Executor = field(default_factory=Executor, init=False, repr=False)
    _input: str | None = field(default=None, init=False, repr=False)
    _args: list[PopenArgs] = field(default_factory=list, init=False, repr=False)

    def __repr__(self) -> str:
        names = ["return_code", "stdout", "stderr"]
        items = [f"{name}={getattr(self, name)!r}" for name in names]
        return f"{type(self).__name__}({', '.join(items)})"

    @property
    def return_code(self):
        self.execute()
        return self._executor.return_code

    @property
    def stdout(self):
        self.execute()
        return self._executor.stdout

    @property
    def stderr(self):
        self.execute()
        return self._executor.stderr

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
        if self._args:
            self._executor(self._args).close()
            self._args.clear()
        return self

    @contextmanager
    def inject(self) -> Iterator[Popen]:
        with self._executor(self._args):
            self._args.clear()
            yield self._executor._processes[-1]

    def _add_args(
        self,
        command: str,
        stderr_to_stdout: bool = False,
        stderr_as_stdin: bool = False,
        fallback_stdout: int | None = None,
        fallback_stderr: int | None = None,
    ) -> PopenArgs:
        kwargs: Kwargs = dict(
            stdout=fallback_stdout,
            stderr=subprocess.STDOUT if stderr_to_stdout else fallback_stderr,
            stdin=None,
            encoding="utf-8",
            text=True,
        )
        args = PopenArgs(
            StdinType.NOINPUT, (shlex.split(command),), kwargs, self._input
        )

        if self._args:
            prev_stdout = self._args[-1].kwargs.get("stdout")
            prev_stderr = self._args[-1].kwargs.get("stderr")

            if prev_stderr in (subprocess.PIPE, None) and stderr_as_stdin:
                self._args[-1].kwargs["stderr"] = subprocess.PIPE
                args.stdin = StdinType.STDERR
            elif prev_stderr == subprocess.STDOUT or prev_stdout == subprocess.PIPE:
                args.stdin = StdinType.STDOUT
        elif self._input is not None:
            args.stdin = StdinType.PIPE
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
