# calendar

Rows with a date (or a start and an end) on month, week, day and list grids. A click opens the record; dragging an
event (or resizing one with an end) proposes the new date through `host.propose` and puts it back unless the host
says ok. A date-only value stays date-only; a date-time keeps its own UTC offset.

- **Keys:** `start` (required), `end`, `title`, `calendarView: month | week | day | list | resourceTimeline` (the
  toolbar's grid buttons write it back with `host.setView`), `groupBy` (event colour, and the resources of the
  resourceTimeline grid), `filters`. A row without an end is drawn as one day (date-only) or one hour (date-time);
  the data is never given that end.
- **Stock:** `@event-calendar/build` 5.18.1 (vkurko, MIT); its `--ec-*` properties are mapped onto `--dv-*` in
  `src/calendar.css`.
- **`src/capture.js`:** the build ships only an IIFE with no export, so this module catches its namespace object as
  it is created (see the file). Replace it with a plain import once `@event-calendar/core` (ESM) is installed.
