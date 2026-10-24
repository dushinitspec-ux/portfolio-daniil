# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them.

---

## 1. The demo crashed on Turkish text when its output was redirected

**What broke.** The first run of the terminal demo with its output piped to another program
stopped on the third guest:

```
File "app/demo.py", line 32, in show
    print(f"\n[{speaker}]\n{text}")
File "...\encodings\cp1251.py", line 19, in encode
UnicodeEncodeError: 'charmap' codec can't encode character 'ı' in position 17
```

The first two guests (English and Russian) printed fine. `ı` is the Turkish dotless
**ı** in "Mehmet Yılmaz".

**Root cause.** When Python on Windows writes to a real console, it uses Unicode. When the
output goes to a pipe or a file (CI logs, `> out.txt`, `| more`), it falls back to the
system's ANSI code page, which on a Russian Windows is cp1251. cp1251 has Cyrillic, so the
Russian guest worked, but it has no Turkish letters. The bug was invisible in a normal
terminal and would have broken any automated run of the demo.

**Fix.** Force UTF-8 on stdout before printing anything:

```python
# before
def main() -> None:
    parser = argparse.ArgumentParser(description="Hotel concierge terminal demo")
```

```python
# after
def main() -> None:
    # When output goes to a pipe or a file, Windows Python encodes it with the ANSI code
    # page (cp1251 on a Russian system), which has no Turkish "ı" - force UTF-8.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Hotel concierge terminal demo")
```

**Lesson.** A multilingual app must be tested with every alphabet it supports, and not only
in an interactive terminal.

---

## 2. Guest commands were sent to the LLM and to reception as questions

**What broke.** Nothing crashed, and the test passed. While writing the end-to-end test
for `/reload`, I traced what happens when a guest (not an admin) sends it. The admin-only
handler correctly ignored the guest, so the message fell through to the "any text from a
guest" handler. The bot paid for an LLM call, found nothing in the knowledge base, and posted
"/reload" to the staff group as a guest question. The same happened to `/help` or any other
command a guest tries.

**Root cause.** aiogram checks handlers in registration order and uses the first one whose
filters match. Commands that a guest may not use matched nothing until the catch-all text
handler, which treats every text as a question.

**Fix.** A handler for commands in private chats, registered before the catch-all, shows
the welcome text instead:

```python
# before
router.message.register(on_staff_reply, IsStaffChat(), F.reply_to_message, F.text)
router.message.register(on_guest_text, private, F.text)
```

```python
# after
router.message.register(on_staff_reply, IsStaffChat(), F.reply_to_message, F.text)
# /help or a command the guest may not use: show the welcome text, do not ask the LLM.
router.message.register(cmd_start, private, F.text.startswith("/"))
router.message.register(on_guest_text, private, F.text)
```

The test now checks that the guest gets the welcome text and that **nothing** reaches the
staff group.

**Lesson.** A test that only checks "the bad thing did not happen" can pass for the wrong
reason. Also check that the right thing happened.
