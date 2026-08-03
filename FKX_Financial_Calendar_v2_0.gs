/**
 * FKX Financial Calendar v2.0
 * Transport: FKX GitHub weekly mirror.
 * Content lineage: Fair Economy / Forex Factory.
 */
const FKX_FINANCIAL_CALENDAR_V2_CFG = Object.freeze({
  SHEET: 'FKX Financial Calendar',
  MIRROR_URL: 'https://raw.githubusercontent.com/OWNER/REPO/main/calendar/current_week.json',
  TZ: 'America/New_York',
  DATA_ROW: 5
});

function FKX_FINANCIAL_CALENDAR_REFRESH_V2_0() {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(FKX_FINANCIAL_CALENDAR_V2_CFG.SHEET);
  if (!sh) throw new Error('Missing FKX Financial Calendar tab.');

  const now = new Date();
  const expected = FKX_FINANCIAL_CALENDAR_WEEK_BOUNDS_(now);
  let response, payload;

  try {
    response = UrlFetchApp.fetch(FKX_FINANCIAL_CALENDAR_V2_CFG.MIRROR_URL + '?t=' + now.getTime(), {
      method: 'get',
      muteHttpExceptions: true,
      followRedirects: true,
      headers: {'Accept': 'application/json', 'User-Agent': 'FKX-Calendar/2.0'}
    });
  } catch (err) {
    FKX_FINANCIAL_CALENDAR_MARK_STALE_(sh, 'Mirror request failed: ' + err.message, now);
    throw err;
  }

  const status = response.getResponseCode();
  if (status !== 200) {
    FKX_FINANCIAL_CALENDAR_MARK_STALE_(sh, 'Mirror HTTP ' + status, now);
    throw new Error('FKX calendar mirror failed with HTTP ' + status);
  }

  try {
    payload = JSON.parse(response.getContentText());
  } catch (err) {
    FKX_FINANCIAL_CALENDAR_MARK_STALE_(sh, 'Mirror JSON parse failed', now);
    throw err;
  }

  const isCurrent = payload.weekStart === expected.startKey && payload.weekEnd === expected.endKey;
  if (!isCurrent) {
    FKX_FINANCIAL_CALENDAR_MARK_STALE_(
      sh,
      'Latest mirror week ' + payload.weekStart + ' to ' + payload.weekEnd +
      '; expected ' + expected.startKey + ' to ' + expected.endKey,
      now
    );
    throw new Error('FKX calendar mirror is stale.');
  }

  const events = (payload.events || [])
    .map(e => ({
      title: String(e.title || '').trim(),
      category: String(e.category || '').trim(),
      dateTime: new Date(e.dateTime),
      source: String(e.source || payload.source || '').trim()
    }))
    .filter(e => e.title && !isNaN(e.dateTime.getTime()))
    .sort((a,b) => a.dateTime - b.dateTime);

  if (!events.length) {
    FKX_FINANCIAL_CALENDAR_MARK_STALE_(sh, 'Current-week mirror contains no selected events', now);
    throw new Error('Current-week mirror contains no selected events.');
  }

  const clearRows = Math.max(sh.getMaxRows() - FKX_FINANCIAL_CALENDAR_V2_CFG.DATA_ROW + 1, 1);
  sh.getRange(FKX_FINANCIAL_CALENDAR_V2_CFG.DATA_ROW, 1, clearRows, 8).clearContent();

  const todayKey = Utilities.formatDate(now, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'yyyy-MM-dd');
  const weekLabel = Utilities.formatDate(expected.start, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'MMM d') +
    '–' + Utilities.formatDate(expected.end, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'd');

  const values = events.map(e => {
    const dateKey = Utilities.formatDate(e.dateTime, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'yyyy-MM-dd');
    const timing = dateKey === todayKey ? 'TODAY' : (e.dateTime > now ? 'UPCOMING' : 'PAST');
    return [
      dateKey,
      Utilities.formatDate(e.dateTime, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'EEEE'),
      Utilities.formatDate(e.dateTime, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'h:mm a'),
      e.category,
      e.title,
      timing,
      weekLabel,
      dateKey + '|' + Utilities.formatDate(e.dateTime, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'HH:mm') + '|' + e.title
    ];
  });

  sh.getRange(FKX_FINANCIAL_CALENDAR_V2_CFG.DATA_ROW, 1, values.length, 8).setValues(values);

  const statusLabel = payload.status === 'CURRENT'
    ? '✅ CURRENT — ' + weekLabel + ' — ' + values.length + ' selected events'
    : '🟡 CURRENT — retained current-week mirror — ' + values.length + ' selected events';

  sh.getRange('C3').setValue(statusLabel);
  sh.getRange('G3').setValue(
    Utilities.formatDate(now, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'yyyy-MM-dd HH:mm') + ' ET'
  );

  SpreadsheetApp.flush();
  ss.toast('FKX Financial Calendar refreshed: ' + values.length + ' events', 'FKX Calendar', 5);
}

function FKX_FINANCIAL_CALENDAR_WEEK_BOUNDS_(now) {
  const tz = FKX_FINANCIAL_CALENDAR_V2_CFG.TZ;
  const localDate = Utilities.formatDate(now, tz, 'yyyy-MM-dd');
  const noon = new Date(localDate + 'T12:00:00-04:00');
  const day = Number(Utilities.formatDate(noon, tz, 'u')); // Mon=1 ... Sun=7
  const daysSinceSunday = day % 7;
  const start = new Date(noon.getTime() - daysSinceSunday * 86400000);
  start.setHours(0,0,0,0);
  const end = new Date(start.getTime() + 6 * 86400000);
  end.setHours(23,59,59,999);
  return {
    start: start,
    end: end,
    startKey: Utilities.formatDate(start, tz, 'yyyy-MM-dd'),
    endKey: Utilities.formatDate(end, tz, 'yyyy-MM-dd')
  };
}

function FKX_FINANCIAL_CALENDAR_MARK_STALE_(sh, reason, now) {
  const rows = sh.getRange('A5:G80').getDisplayValues();
  let retainedWeek = '';
  for (let i = 0; i < rows.length; i++) {
    if (rows[i][6]) { retainedWeek = rows[i][6]; break; }
  }
  sh.getRange('C3').setValue(
    '🔴 STALE — ' + reason + (retainedWeek ? '; retained week ' + retainedWeek : '')
  );
  sh.getRange('G3').setValue(
    Utilities.formatDate(now, FKX_FINANCIAL_CALENDAR_V2_CFG.TZ, 'yyyy-MM-dd HH:mm') + ' ET'
  );
}
