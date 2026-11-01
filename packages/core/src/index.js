/* data-ui: the core bundle (dist/data-ui.js). Importing it defines <data-views>, <data-facets> and <data-value> and
   registers the built-in views; each view's code loads on first use from dist/views/. The contract every view and
   host builds on is docs/CONTRACT.md. */

export * as grammar from './grammar.js';
export { FRAMES, frameOf, scrollParent, offsetIn, scrollOptions, syncMargin, scrollToStart } from './frame.js';
export { CALCULATIONS, SUMMARIES, SUMMARY_ALIASES, summaryName, rollup, rollupKeep, rollupDims, rolledAway, DISPLAYS, summarize, compileExpression, compileFilters, filterList, pivot, PIVOT_PREFIX, toBaseYaml, viewKey, encodeView, decodeView, cellValue } from './grammar.js';
export { TIME_GRAINS, timeBucket, bucketLabel, bucketStart, nextBucket } from './grammar.js';
// the grouped gallery (docs/CONTRACT.md §20): numeric bins, groupings, sections, the nav facet's groups
export { binsOf, binKey, groupingOf, effectiveView, pathSep, pathSegments, viewPath } from './grammar.js';
export { sectionsOf, groupEntries, groupText } from './rowmodel.js';
export { groupBuckets, groupFacet, allSpecs, fmtUnit } from './facets.js';
export { VISIBILITY, visibilityOf, columnIds, inspectorProperties, moreLabel, moreHtml, visibilityButton, addPropertyHtml, wordOf } from './inspector.js';
export { parseBase, parseBaseWithLines, stringifyBase, replaceViewInText, replaceKeyInText, lineOf, BaseSyntaxError } from './base.js';
// Add to dashboard (docs/CONTRACT.md §34): the pure half, for a host that appends a panel itself
export { appendPanel, relativePath, andFilters } from './add-to-dashboard.js';
export { dashboardsHook, handOver, openItemMenu } from './add-picker.js';
// source precedence (docs/CONTRACT.md §36): which of a value's stated sources is nominal (pure)
export { isMultiSource, entryOf, stated, conflict, differs, byPrecedence, pick, agreement, changed, held, inPlace, ladderOrder, sourceIds, fieldsOf, normalizeOrder, normalizePicks, entryCell, resolveCell, resolveDataset, precedenceOf, encodeOrder, decodeOrder, encodePicks, decodePicks, sourceRows, sourcedProperties, sourceColumnOf, nominalSource, columnId, unfoldDataset, formulaView, slotOrder, orderAfter, placeShown, ownColumns, sourcesView, setSourceValue, foldEdit } from './precedence.js';
// the source popover (docs/CONTRACT.md §36): the item menu of a value two or more sources state, and the mark a view writes on it
export { sourcesMenu, PIN } from './source-popover.js';
export { rowModel, tableModel, properties, search, pivotProperties, treeSpec, treeRows, isHeading, bareView, PROPERTY_KEYS, pathRows, pathGroup } from './rowmodel.js';
// the row model in a worker (review 2026-10-26 item 10): <data-views> uses it at WORKER_ROWS rows and up (rowmodel-worker.js)
export { createRowModelWorker, modelFromOrder, workerEligible, WORKER_ROWS } from './rowmodel-worker.js';
export { normalizeDataset, parseCSV, parseRecords, parseJSONL, loadDataset, fieldToProperty, inferProperties } from './data.js';
// a pasted block (docs/CONTRACT.md §40): what is one, what each value becomes, where each lands (pure)
export { parseBlock, isBlock, coerceCell, planPaste, KINDS as COLUMN_KINDS, KIND_LABEL, kindOf, definitionFor, propertyKey, fits, dropFromView, restoreToView, columnFilter, setColumnFilter, choicesOf } from './sheet.js';
export { registerView, viewPlugin, listViews, loadView } from './registry.js';
export { resolveTokens, toRgb, TOKENS, SERIES, BASES, TONE_NAMES } from './tokens.js';
export { markdown } from './md.js';
export { PROPERTY_TYPES, TYPE_PICKER, ICONS, ICON_NAMES, COLORS, STATUS_GROUPS, typeOf, optionOf, optionList, colorOf, statusGroup, formatText, typedHtml, typeIconHtml, isRich, hasFormat, relationContext } from './types.js';
export { h1Sections, setH1, expandH1, liftH1 } from './markdown-columns.js';
export { pageLayout, pageOn, freeProperty, layoutValue, stepEntry, moveEntry, withPlace, withVisible, PLACES } from './page-layout.js';
export { sectionCell, outlineOf, mediaOf, isDerivedCell, esc, fmtNum, fmtClock, fmtAge, numOpts, exactText, valueText, cellText, withValue, attachmentsOf, thumbsHtml, linkCell, isLinkTarget, valueHtml, provenanceAttr, sourcesAttr, mediaUrl, propLabel, groupLabel, hueOf, slug, shortDate, BASIS, isNum, isEmpty } from './format.js';
export { toRail, fromRail, parseClause, ref, matchesFacet, matchesRail, facetCounts, KINDS, facetSpecs, railConfig, railCounts, railParams, paramsRail, histogram, bucketsOf } from './facets.js';
// a facet's parent: (CONTRACT §7): a picker's click settles the facets nested under its pick as the rail does (CONTRACT §33)
export { settleChildren, descendants } from './facets.js';
export { fieldHtml, readEdits, lockedBecause } from './form.js';
export { makeResizable, autoResize, resizeKit } from './resize.js';
// one playback time per dashboard (docs/peps/0005-dashboard-cards.md §4)
export { Clock, clockFor, followVideo, fmtTime, seriesColor, primaryDriver, driverInstance, driverKey, readClockParams, writeClockParams, clockNavigation } from './clock.js';
// the series legend every chart draws: click hides, double-click / Alt + click isolates, the hidden set in the URL
export { legendClick, legendPress, nextHidden, hiddenAfter, hiddenOf, encodeHidden, decodeHidden, legendKey, readLegendParams, writeLegendParams, SeriesLegend } from './legend.js';
// rules and bands from a property (PEP 0010 P2, sim2real gap #6): what the time series and the live plot draw
export { guidesFrom, guidesNameProperty, limitGuides } from './guides.js';
// the diagnostics and gates overlay (docs/CONTRACT.md §35): the status vocabulary, and the side peek's sections
export { STATUS, STATUS_ORDER, TONE_GLYPH, statusOf, worstStatus, statusHtml } from './status.js';
export { bindThis, bindFilters, peekSections, sectionSources, linkHtml } from './sections.js';
export { fromControl } from './open.js';
export { parseQuery, formatQuery, clauseToken, suggest } from './toolbar/query.js';
export { Selection, DEFAULT_ACTIONS, resolveActions } from './toolbar/selection.js';
// live data and rewind (docs/peps/0012-live-data.md, CONTRACT §26): LiveDataset, LiveClock, sources, the frame loop
export * from './live.js';
// shared stock parts, so every view bundle uses the page's one copy
export { Virtualizer, elementScroll, observeElementOffset, observeElementRect, windowScroll, observeWindowOffset, observeWindowRect } from '@tanstack/virtual-core';
export { DataViews, PLANNED_TYPES } from './elements/data-views.js';
export { DataFacets } from './elements/data-facets.js';
export { DataValue } from './elements/data-value.js';
export { DataMesh, meshEngine } from './elements/data-mesh.js';
// the app rail (docs/CONTRACT.md §27): <data-rail>, its three styles, and the settings select
export { DataRail, bindRailSelect } from './rail/data-rail.js';
export { RAIL_MODES, RAIL_MODE_OPTIONS, isRailMode } from './rail/model.js';
import './builtins.js';
import { autoResize } from './resize.js';

// every host panel marked data-resizable="left|right" gets its handle (docs/CONTRACT.md §11); the kit's own panels get
// theirs when their <data-views> starts
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => autoResize(), { once: true });
  else autoResize();
}

export const version = 'DATA_UI_VERSION';
