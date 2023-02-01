from shell import Shell

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

