# Bugs found and fixed

Real bugs I hit while building this project. The main one showed up the first time I ran the
tool on its own sample shop, where I knew every planted mistake and could compare the counts.

---

## 1. The home page was analysed twice, so its problems were counted twice

**What broke.** The first CLI run on the broken sample shop reported:

```
5 of 6 pages analysed in 2.22 s; robots.txt found and obeyed.
  FAIL  1.4.4  Resize Text (AA)  2 issues on 2 pages
  FAIL  3.1.1  Language of Page (A)  3 issues on 3 pages
```

Only the home page has the viewport tag that blocks zoom, and only two pages have a language
problem. The numbers were wrong, and a shop owner would have been told about a zoom problem on
"2 pages".

**Root cause.** The crawl starts at `/samples/broken/`, and the menu on that page links to
`index.html`. The server returns the same document for both URLs. URL normalisation cannot know
that `/` and `/index.html` are the same page (on another server they may not be), so the crawler
fetched and analysed the same HTML twice, and every issue of the home page was counted twice.
The old de-duplication only caught redirects that ended on an already scanned URL.

**Fix.** Hash the HTML body (SHA-256) when it is read. A page whose body is identical to a page
already analysed is still listed (with its status code), marked `duplicate_of`, and neither
analysed nor followed again:

```python
# before
if page.final_url != page.url and page.final_url in self._final_urls:
    page.error = page.error or f"Redirects to {page.final_url}, which is already scanned"
    page.soup = None
self._final_urls.add(page.final_url)
```

```python
# after
if page.final_url != page.url and page.final_url in self._final_urls:
    page.duplicate_of = self._final_urls[page.final_url]
elif page.body_hash and page.body_hash in self._hashes:
    page.duplicate_of = self._hashes[page.body_hash]
if page.duplicate_of:
    page.soup = None  # same document: do not analyse it or follow its links again
else:
    self._final_urls.setdefault(page.final_url, page.url)
    if page.body_hash:
        self._hashes[page.body_hash] = page.url
```

The same run now says `4 of 6 pages analysed`, `1 issue on 1 page` for 1.4.4 and `2 issues on
2 pages` for 3.1.1. A crawler test serves identical HTML at `/` and `/index.html` and checks that
only one of them is analysed, and the sample-shop test pins the exact number of findings per rule.

**Lesson.** Run the tool on a site where you know every planted mistake and compare the counts,
not just "does it find something".

---

## 2. The limitations paragraph was shown twice

**What broke.** On the first screenshot of a report with a shop-owner summary, the paragraph
"This is an automated check of the HTML only..." appeared twice, one block under the other.

**Root cause.** The report always ends its "Not checked automatically" section with that
paragraph, and the offline explainer also put the same text into `explanation.note`, which the
template printed under the summary.

**Fix.** Print the note only when it says something the page does not already say (for example
that Claude was unavailable, or that the fixed texts exist only in English):

```html
<!-- before -->
{% if report.explanation.note %}<p class="notice">{{ report.explanation.note }}</p>{% endif %}
```

```html
<!-- after -->
{% if report.explanation.note and report.explanation.note != limits_note %}<p class="notice">{{ report.explanation.note }}</p>{% endif %}
```

The note stays in the JSON export, where the limits section of the page does not exist.
