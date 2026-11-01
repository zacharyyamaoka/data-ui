# Releases and daily notes

robotparts' release tags and the dates of Zach's daily notes on one calendar: a month grid, a list, and the
latest release week. Only file names and frontmatter dates are read from the vault, never a note's text. Drag an
event to another day: the view proposes the new date to the host, and this page (`site.json`: editable) applies it
in memory; a read-only page refuses and the event goes back.

- **App:** robotparts
- **Replaces:** scanning `Sources/Daily Notes/` by file name and `git tag -l 'release/*'`; there was no calendar of
  either.
- **Shows:** the calendar view (Event Calendar) with `start`, `title`, `calendarView` (month, list, week; the
  toolbar's buttons write it back), `groupBy` as event colour, a filter, drag-to-reschedule through
  `host.propose`, and the same rows as a table.
- **Data:** `calendar.json`, written by `source/build.py`: 166 daily notes (title = file name, date from it,
  `date created` / `date modified` from frontmatter) and 6 releases (tag date-time and commit).
