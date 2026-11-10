## read_file
Read a file before you change it, and only the part you need of a long one.

## list_dir
Look at a directory to learn how a project is laid out.

## glob
Find files by name; prefer it to listing directory after directory.

## grep
Find where something is defined or used; search before you read files one by
one.

## write_file
Create new files. For a change to a file that exists, use edit_file.

## edit_file
Change part of a file. Copy old_string exactly from what read_file showed,
without the line numbers.

## run_command
Run tests, builds and other commands; after a change, run the tests that
cover it. Prefer the project's own commands (its instructions often name
them). Never run a command that waits for input.

## todo_write
Only for work of three or more separate changes: plan it before you start
and keep it current. Each task is a change to make, never a read or a check.
Send each update in the same reply as the call that starts the next task,
and the last one with your last change: never end with a stale list. Never
for one or two edits, nor for a question.

## ask_user
Ask only when you cannot go on without the answer and the project does not
give it: a choice between real options. Never to confirm a plan, nor what
the tools can find.
