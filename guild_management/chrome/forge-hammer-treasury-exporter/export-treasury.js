(() => {
  'use strict';

  const triggerKey = 'forge-hammer-treasury-export';
  const triggerParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const manualCapture = triggerParams.get('manual_capture') === '1';
  if (!triggerParams.get(triggerKey) && !manualCapture) return;

  const exportTreasury = !manualCapture && triggerParams.get('treasury') !== '0';
  const exportContributions = manualCapture || triggerParams.get('contributions') === '1';
  const contributionCutoffText = triggerParams.get('contribution_cutoff');
  const runMarker = '__goeForgeHammerDataExportStarted';
  if (window[runMarker]) return;
  window[runMarker] = true;

  const showClanEventName =
    'de.innogames.strategycity.shared.ui.window.clans.controller.ShowClanWindowCommand_Event';
  const conversationWindowEventName =
    'de.innogames.strategycity.shared.event.ConversationWindowEvent';
  const clanLogModelName =
    'de.innogames.strategycity.main.model.ClanTreasuryLogModel';
  const baseDispatcherName = 'openfl.events.EventDispatcher';
  const moduleDispatcherName = 'org.robotlegs.utilities.modular.base.ModuleEventDispatcher';
  const showClanEventType =
    'de.innogames.strategycity.shared.ui.window.clans.controller.ShowClanWindowCommand/EVENT_TYPE';
  const contributionEventType = 'ConversationWindowEvent/OPEN_GUILD_CONTRIBUTION';
  const messageCenterEventType = 'ConversationWindowEvent/REQUEST_MESSAGE_CENTER';
  const contributionPageSize = 10;
  const contributionPageDelayMs = 300;
  const timeoutMs = 120_000;
  const pollMs = 250;
  const statusId = 'goe-forge-hammer-export-status';
  const capturedManualEventTypes = new Set([
    'ConversationWindowEvent/REQUEST_MESSAGE_CENTER',
    'ConversationWindowEvent/OPEN_GUILD_CONTRIBUTION',
    'ClanTreasuryLogEvent/GET_PAGE',
  ]);
  const gameHooks = {
    classes: new Map(),
    dispatchers: new Set(),
    clanLogModel: null,
    restoreNameCapture: null,
    restoreBaseDispatcher: null,
    restoreDispatcher: null,
    restoreClanLogModel: null,
    treasuryTriggerStarted: false,
    messageCenterTriggerStarted: false,
    contributionTriggerStarted: false,
  };

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const manualLog = (kind, data) => {
    if (!manualCapture) return;
    console.info('[GoE manual capture] ' + JSON.stringify({
      capturedAt: new Date().toISOString(),
      kind,
      ...data,
    }));
  };

  const setStatus = (message, state = 'working') => {
    let element = document.getElementById(statusId);
    if (!element) {
      element = document.createElement('div');
      element.id = statusId;
      Object.assign(element.style, {
        position: 'fixed',
        zIndex: '2147483647',
        top: '12px',
        left: '50%',
        transform: 'translateX(-50%)',
        padding: '10px 14px',
        borderRadius: '6px',
        color: '#fff',
        font: '600 14px/1.3 system-ui, sans-serif',
        boxShadow: '0 2px 12px rgba(0, 0, 0, .45)',
      });
      document.documentElement.appendChild(element);
    }
    element.style.background = state === 'error' ? '#9f2525' : state === 'done' ? '#216e39' : '#2f506f';
    element.textContent = message;
  };

  const waitUntil = async (predicate, message) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const value = await predicate();
      if (value) return value;
      await sleep(pollMs);
    }
    throw new Error(message);
  };

  // ForgeHX keeps its class registry private, but assigns each Haxe class its
  // stable, fully-qualified __name__. Capture only the classes required to
  // dispatch the same events and page changes as the game UI.
  const installGameClientHooks = () => {
    const originalNameDescriptor = Object.getOwnPropertyDescriptor(Function.prototype, '__name__');
    const wantedNames = new Set([moduleDispatcherName]);
    if (exportContributions) wantedNames.add(baseDispatcherName);
    if (exportTreasury) wantedNames.add(showClanEventName);
    if (exportContributions) {
      wantedNames.add(conversationWindowEventName);
      wantedNames.add(clanLogModelName);
    }
    let captureInstalled = false;

    const restoreNameCapture = () => {
      if (!captureInstalled) return;
      if (originalNameDescriptor) {
        Object.defineProperty(Function.prototype, '__name__', originalNameDescriptor);
      } else {
        delete Function.prototype.__name__;
      }
      captureInstalled = false;
    };
    gameHooks.restoreNameCapture = restoreNameCapture;

    const armBaseDispatcherCapture = () => {
      if (!exportContributions || gameHooks.restoreBaseDispatcher) return;
      const DispatcherClass = gameHooks.classes.get(baseDispatcherName);
      if (!DispatcherClass?.prototype) return;

      const prototype = DispatcherClass.prototype;
      const originalDispatcher = prototype.dispatchEvent;
      const originalAddListener = prototype.addEventListener;
      if (typeof originalDispatcher !== 'function' || typeof originalAddListener !== 'function') return;
      const wrappedDispatcher = function (event) {
        gameHooks.dispatchers.add(this);
        if (capturedManualEventTypes.has(event?.type)) {
          manualLog('event-dispatched', {
            eventType: event.type,
            dispatcherClass: this?.__class__?.__name__ || null,
          });
        }
        return originalDispatcher.call(this, event);
      };
      const wrappedAddListener = function (...args) {
        gameHooks.dispatchers.add(this);
        if (capturedManualEventTypes.has(args[0])) {
          manualLog('listener-added', {
            eventType: args[0],
            dispatcherClass: this?.__class__?.__name__ || null,
          });
        }
        return originalAddListener.apply(this, args);
      };
      prototype.dispatchEvent = wrappedDispatcher;
      prototype.addEventListener = wrappedAddListener;
      gameHooks.restoreBaseDispatcher = () => {
        if (prototype.dispatchEvent === wrappedDispatcher) prototype.dispatchEvent = originalDispatcher;
        if (prototype.addEventListener === wrappedAddListener) prototype.addEventListener = originalAddListener;
      };
    };

    const armModuleDispatcherCapture = () => {
      if (gameHooks.restoreDispatcher) return;
      const DispatcherClass = gameHooks.classes.get(moduleDispatcherName);
      if (!DispatcherClass || typeof DispatcherClass.prototype?.dispatchEvent !== 'function') return;

      const prototype = DispatcherClass.prototype;
      const hadOwnDispatcher = Object.prototype.hasOwnProperty.call(prototype, 'dispatchEvent');
      const hadOwnAddListener = Object.prototype.hasOwnProperty.call(prototype, 'addEventListener');
      const originalDispatcher = prototype.dispatchEvent;
      const originalAddListener = prototype.addEventListener;
      const wrappedDispatcher = function (event) {
        gameHooks.dispatchers.add(this);
        return originalDispatcher.call(this, event);
      };
      const wrappedAddListener = function (...args) {
        gameHooks.dispatchers.add(this);
        return originalAddListener.apply(this, args);
      };
      prototype.dispatchEvent = wrappedDispatcher;
      if (typeof originalAddListener === 'function') {
        prototype.addEventListener = wrappedAddListener;
      }
      gameHooks.restoreDispatcher = () => {
        if (prototype.dispatchEvent === wrappedDispatcher) {
          if (hadOwnDispatcher) prototype.dispatchEvent = originalDispatcher;
          else delete prototype.dispatchEvent;
        }
        if (prototype.addEventListener === wrappedAddListener) {
          if (hadOwnAddListener) prototype.addEventListener = originalAddListener;
          else delete prototype.addEventListener;
        }
      };
    };

    const armClanLogModelCapture = () => {
      if (!exportContributions || gameHooks.restoreClanLogModel) return;
      const ModelClass = gameHooks.classes.get(clanLogModelName);
      if (!ModelClass?.prototype) return;

      const prototype = ModelClass.prototype;
      const originals = new Map();
      for (const methodName of ['init', 'set_currentPage', 'set_clanTreasuryLogsVO']) {
        const original = prototype[methodName];
        if (typeof original !== 'function') continue;
        const wrapped = function (...args) {
          gameHooks.clanLogModel = this;
          return original.apply(this, args);
        };
        originals.set(methodName, { original, wrapped });
        prototype[methodName] = wrapped;
      }
      gameHooks.restoreClanLogModel = () => {
        for (const [methodName, methods] of originals) {
          if (prototype[methodName] === methods.wrapped) {
            prototype[methodName] = methods.original;
          }
        }
      };
    };

    const armCapturedClasses = () => {
      armBaseDispatcherCapture();
      armModuleDispatcherCapture();
      armClanLogModelCapture();
    };

    try {
      Object.defineProperty(Function.prototype, '__name__', {
        configurable: true,
        get() {
          return originalNameDescriptor?.get
            ? originalNameDescriptor.get.call(this)
            : originalNameDescriptor?.value;
        },
        set(value) {
          Object.defineProperty(this, '__name__', {
            configurable: true,
            enumerable: true,
            writable: true,
            value,
          });
          if (wantedNames.has(value)) {
            gameHooks.classes.set(value, this);
            if (gameHooks.classes.size === wantedNames.size) {
              restoreNameCapture();
              Promise.resolve().then(armCapturedClasses);
            }
          }
        },
      });
      captureInstalled = true;
    } catch (error) {
      restoreNameCapture();
      throw new Error(`Could not install the game-client hook: ${error.message}`);
    }

    window.addEventListener('pagehide', restoreNameCapture, { once: true });
  };

  const findDispatcher = eventType => {
    for (const dispatcher of gameHooks.dispatchers) {
      try {
        if (dispatcher.hasEventListener(eventType)) return dispatcher;
      } catch (_error) {
        // Ignore a dispatcher belonging to a module that has already shut down.
      }
    }
    return null;
  };

  const triggerGameTreasuryRefreshOnce = dispatcher => {
    if (gameHooks.treasuryTriggerStarted) {
      throw new Error('The treasury refresh trigger was already used; no retry was made.');
    }
    gameHooks.treasuryTriggerStarted = true;
    const ShowClanWindowEvent = gameHooks.classes.get(showClanEventName);
    if (typeof ShowClanWindowEvent !== 'function') {
      throw new Error('The game treasury event class is unavailable; no request was sent.');
    }
    dispatcher.dispatchEvent(new ShowClanWindowEvent(null, 'treasury'));
  };

  const triggerContributionLogOnce = dispatcher => {
    if (gameHooks.contributionTriggerStarted) {
      throw new Error('The contribution-log trigger was already used; no retry was made.');
    }
    gameHooks.contributionTriggerStarted = true;
    const ConversationWindowEvent = gameHooks.classes.get(conversationWindowEventName);
    if (typeof ConversationWindowEvent !== 'function') {
      throw new Error('The game contribution event class is unavailable; no request was sent.');
    }
    dispatcher.dispatchEvent(new ConversationWindowEvent(contributionEventType));
  };

  const triggerMessageCenterOnce = dispatcher => {
    if (gameHooks.messageCenterTriggerStarted) {
      throw new Error('The Message Center trigger was already used; no retry was made.');
    }
    gameHooks.messageCenterTriggerStarted = true;
    const ConversationWindowEvent = gameHooks.classes.get(conversationWindowEventName);
    if (typeof ConversationWindowEvent !== 'function') {
      throw new Error('The game Message Center event class is unavailable; no request was sent.');
    }
    dispatcher.dispatchEvent(new ConversationWindowEvent(messageCenterEventType));
  };

  const createTreasuryRequestObserver = () => {
    let outgoingRequest = null;
    let response = null;
    let observerError = null;

    const stop = () => {
      FH.proxy.removeRequestHandler('ClanService', 'getTreasuryBag', requestHandler);
      FH.proxy.removeHandler('ClanService', 'getTreasuryBag', responseHandler);
    };
    const requestHandler = request => {
      if (!gameHooks.treasuryTriggerStarted || outgoingRequest) return;
      outgoingRequest = request;
      FH.proxy.removeRequestHandler('ClanService', 'getTreasuryBag', requestHandler);
      const bagType = request?.requestData?.[0]?.value;
      if (bagType && bagType !== 'ClanMain') {
        observerError = new Error(
          `The game requested treasury bag ${bagType}, not ClanMain; no retry was made.`
        );
      }
      console.info('[GoE data exporter] Treasury request sent once.', {
        requestId: request?.requestId,
        bagType,
      });
    };
    const responseHandler = data => {
      if (!outgoingRequest || data?.requestId !== outgoingRequest.requestId) return;
      response = data;
      stop();
    };
    FH.proxy.addRequestHandler('ClanService', 'getTreasuryBag', requestHandler);
    FH.proxy.addHandler('ClanService', 'getTreasuryBag', responseHandler);
    return {
      getResult() {
        if (observerError) throw observerError;
        return response ? { request: outgoingRequest, response } : null;
      },
      stop,
    };
  };

  const createContributionPageObserver = () => {
    let expectedOffset = 0;
    let activeRequest = null;
    let observerError = null;
    const responses = [];

    const stop = () => {
      FH.proxy.removeRequestHandler('ClanService', 'getTreasuryLogs', requestHandler);
      FH.proxy.removeHandler('ClanService', 'getTreasuryLogs', responseHandler);
    };
    const requestHandler = request => {
      if (!gameHooks.contributionTriggerStarted) return;
      if (activeRequest) {
        observerError = new Error('A second contribution page request started before the first completed.');
        return;
      }
      const [limit, offset, bag] = request?.requestData || [];
      if (limit !== contributionPageSize || offset !== expectedOffset || bag?.value !== 'ClanMain') {
        observerError = new Error(
          `Unexpected contribution page request (limit ${limit}, offset ${offset}, bag ${bag?.value}); no retry was made.`
        );
        return;
      }
      activeRequest = request;
      console.info('[GoE data exporter] Contribution page requested once.', {
        requestId: request.requestId,
        offset,
      });
    };
    const responseHandler = data => {
      if (!activeRequest || data?.requestId !== activeRequest.requestId) return;
      responses.push({ request: activeRequest, response: data });
      activeRequest = null;
    };
    FH.proxy.addRequestHandler('ClanService', 'getTreasuryLogs', requestHandler);
    FH.proxy.addHandler('ClanService', 'getTreasuryLogs', responseHandler);
    return {
      expectOffset(offset) {
        if (activeRequest) throw new Error('Cannot advance while a contribution page is pending.');
        expectedOffset = offset;
      },
      takeResult() {
        if (observerError) throw observerError;
        return responses.shift() || null;
      },
      stop,
    };
  };

  const responseResources = response => (
    response?.responseData?.resources?.resources || response?.responseData?.resources || null
  );

  const startManualCapture = async () => {
    await waitUntil(
      () => (
        typeof FH === 'object' &&
        typeof FH.proxy?.addRequestHandler === 'function' &&
        typeof FH.proxy?.removeRequestHandler === 'function' &&
        typeof FH.proxy?.addHandler === 'function' &&
        typeof FH.proxy?.removeHandler === 'function'
      ),
      'Forge Hammer did not initialize passive capture before the timeout.'
    );
    const requestHandler = request => {
      const [limit, offset, bag] = request?.requestData || [];
      manualLog('treasury-log-request', {
        requestId: request?.requestId ?? null,
        limit: limit ?? null,
        offset: offset ?? null,
        bag: bag?.value ?? null,
      });
    };
    const responseHandler = response => {
      const logs = response?.responseData?.logs;
      manualLog('treasury-log-response', {
        requestId: response?.requestId ?? null,
        count: response?.responseData?.count ?? null,
        rows: Array.isArray(logs) ? logs.length : null,
        firstTimestamp: Array.isArray(logs) && logs.length ? logs[0].createdAt : null,
        lastTimestamp: Array.isArray(logs) && logs.length ? logs[logs.length - 1].createdAt : null,
      });
    };
    const stop = () => {
      FH.proxy.removeRequestHandler('ClanService', 'getTreasuryLogs', requestHandler);
      FH.proxy.removeHandler('ClanService', 'getTreasuryLogs', responseHandler);
    };
    FH.proxy.addRequestHandler('ClanService', 'getTreasuryLogs', requestHandler);
    FH.proxy.addHandler('ClanService', 'getTreasuryLogs', responseHandler);
    window.addEventListener('pagehide', stop, { once: true });
    manualLog('capture-armed', {
      capturedClasses: Array.from(gameHooks.classes.keys()),
    });
    setStatus('Manual Message Center → Contribution List capture is armed.', 'done');
  };
  const sameResourceMap = (actual, expected) => {
    if (!actual || !expected) return false;
    const expectedKeys = Object.keys(expected);
    if (Object.keys(actual).length !== expectedKeys.length) return false;
    return expectedKeys.every(key => Number(actual[key]) === Number(expected[key]));
  };
  const contributionTimestamp = value => {
    let parsed = value;
    if (
      !(value instanceof Date) &&
      typeof EventHandler === 'object' &&
      typeof EventHandler.ParseDate === 'function'
    ) {
      parsed = EventHandler.ParseDate(value) || value;
    }
    const timestamp = parsed instanceof Date ? parsed.getTime() : new Date(parsed).getTime();
    if (!Number.isFinite(timestamp)) throw new Error(`Invalid contribution timestamp: ${value}`);
    return timestamp;
  };

  const exportStoredTreasury = async () => {
    const dispatcher = await waitUntil(
      () => findDispatcher(showClanEventType),
      'The game client did not expose its Treasury action before the timeout; no request was sent.'
    );
    await IndexDB.getDB();
    const observer = createTreasuryRequestObserver();
    try {
      setStatus('Requesting the guild treasury once through the game client…');
      triggerGameTreasuryRefreshOnce(dispatcher);
      const observed = await waitUntil(
        () => observer.getResult(),
        'The one treasury request produced no matching Forge Hammer response; no retry was made.'
      );
      const freshResources = responseResources(observed.response);
      if (!freshResources) {
        throw new Error(
          `Treasury response ${observed.response.requestId} contains no resources; no retry was made.`
        );
      }
      setStatus(`Waiting for Forge Hammer to store request ${observed.response.requestId}…`);
      const currentHour = Number(moment().startOf('hour'));
      const currentDay = Number(moment().startOf('day'));
      await waitUntil(async () => {
        const [hourly, daily] = await Promise.all([
          IndexDB.db.statsTreasureClanH.get(new Date(currentHour)),
          IndexDB.db.statsTreasureClanD.get(new Date(currentDay)),
        ]);
        return (
          hourly && daily &&
          sameResourceMap(hourly.resources, freshResources) &&
          sameResourceMap(daily.resources, freshResources)
        );
      }, 'Forge Hammer observed the response but did not store it; no export or retry was attempted.');
    } finally {
      observer.stop();
    }

    Stats.state.source = 'statsTreasureClanD';
    Stats.state.chartType = 'line';
    Stats.state.isGroupByEra = false;
    Stats.state.isRenormalize = false;
    Stats.state.eras = {};
    Stats.PlayableEras.forEach(era => { Stats.state.eras[era] = true; });
    Stats.DatePickerFrom = null;
    Stats.DatePickerTo = null;
    const result = await Stats.createTreasureSeries();
    const series = result && result.series;
    if (!Array.isArray(series) || series.length !== 110) {
      throw new Error(`Forge Hammer prepared ${series?.length || 0} goods; expected 110.`);
    }
    const timestamps = series.flatMap(item => item.data.map(point => Number(point[0])));
    if (Math.max(...timestamps) !== Number(moment().startOf('day'))) {
      throw new Error('Forge Hammer daily history does not contain today\'s stored snapshot.');
    }
    Stats.exportCSV(series, `stats-${moment().format('YYYY-MM-DD')}.csv`);
  };

  const exportContributionLogs = async () => {
    const cutoff = new Date(contributionCutoffText || '');
    if (!Number.isFinite(cutoff.getTime())) {
      throw new Error('The contribution overlap cutoff is missing or invalid; no request was sent.');
    }
    if (
      typeof Settings !== 'object' ||
      typeof Settings.GetSetting !== 'function' ||
      Settings.GetSetting('ShowGuildTreasuryLogExport') !== true ||
      typeof Treasury !== 'object' ||
      typeof Treasury.Export !== 'function'
    ) {
      throw new Error(
        'Forge Hammer Guild Treasury Export Log is unavailable or disabled; no request was sent.'
      );
    }

    let dispatcher = findDispatcher(contributionEventType);
    if (!dispatcher) {
      const moduleDispatcher = await waitUntil(
        () => findDispatcher(messageCenterEventType),
        'The game client did not expose its Message Center action; no request was sent.'
      );
      setStatus('Opening Message Center once so Guild Contributions can initialize…');
      triggerMessageCenterOnce(moduleDispatcher);
      dispatcher = await waitUntil(
        () => findDispatcher(contributionEventType),
        'Message Center opened, but its Guild Contributions action did not initialize; no contribution request was sent.'
      );
    }
    Treasury.Logs = [];
    const observer = createContributionPageObserver();
    let accumulatedRows = 0;
    let page = 0;
    let stopReason = null;
    try {
      setStatus(`Loading contribution page 1 to overlap ${contributionCutoffText}…`);
      triggerContributionLogOnce(dispatcher);
      while (!stopReason) {
        const observed = await waitUntil(
          () => observer.takeResult(),
          `Contribution page ${page + 1} produced no matching response; no retry was made.`
        );
        const logs = observed.response?.responseData?.logs;
        const totalCount = Number(observed.response?.responseData?.count);
        if (!Array.isArray(logs) || logs.length === 0 || !Number.isFinite(totalCount)) {
          throw new Error(
            `Contribution response ${observed.response?.requestId} is incomplete; no retry was made.`
          );
        }
        accumulatedRows += logs.length;
        await waitUntil(
          () => Array.isArray(Treasury.Logs) && Treasury.Logs.length >= accumulatedRows,
          `Forge Hammer did not append contribution page ${page + 1}; no retry was made.`
        );

        const firstRowTimestamp = contributionTimestamp(logs[0].createdAt);
        const nextOffset = (page + 1) * contributionPageSize;
        if (firstRowTimestamp <= cutoff.getTime()) {
          stopReason = 'overlap_cutoff';
        } else if (logs.length < contributionPageSize || nextOffset >= totalCount) {
          stopReason = 'server_exhausted';
        } else {
          const model = await waitUntil(
            () => gameHooks.clanLogModel,
            'The game contribution pagination model did not initialize; no further request was sent.'
          );
          page += 1;
          observer.expectOffset(page * contributionPageSize);
          setStatus(
            `Loading contribution page ${page + 1}; ${accumulatedRows} rows captured…`
          );
          // Match the cadence of the captured manual next-page flow instead of
          // issuing pages in a tight loop.
          await sleep(contributionPageDelayMs);
          model.set_currentPage(page);
        }
      }
    } finally {
      observer.stop();
    }

    if (!Array.isArray(Treasury.Logs) || Treasury.Logs.length !== accumulatedRows) {
      throw new Error('Forge Hammer contribution row count changed before export.');
    }
    console.info('[GoE data exporter] Contribution pagination complete.', {
      pages: page + 1,
      rows: accumulatedRows,
      cutoff: contributionCutoffText,
      stopReason,
    });
    Treasury.Export();
  };

  installGameClientHooks();

  const run = async () => {
    if (!exportTreasury && !exportContributions) {
      throw new Error('No Forge Hammer export was requested.');
    }
    setStatus('Waiting for the game and Forge Hammer…');
    await waitUntil(
      () => (
        typeof FH === 'object' &&
        typeof FH.proxy?.addRequestHandler === 'function' &&
        typeof FH.proxy?.removeRequestHandler === 'function' &&
        typeof FH.proxy?.addHandler === 'function' &&
        typeof FH.proxy?.removeHandler === 'function' &&
        typeof moment === 'function' &&
        (!exportTreasury || (
          typeof Stats === 'object' &&
          typeof IndexDB === 'object' &&
          Array.isArray(Stats.PlayableEras) &&
          Stats.PlayableEras.length > 0
        )) &&
        (!exportContributions || (
          typeof Settings === 'object' &&
          typeof Treasury === 'object'
        ))
      ),
      'Forge Hammer did not initialize before the timeout; no requested game action was sent.'
    );

    if (exportTreasury) await exportStoredTreasury();
    if (exportContributions) await exportContributionLogs();

    gameHooks.restoreClanLogModel?.();
    gameHooks.restoreBaseDispatcher?.();
    gameHooks.restoreDispatcher?.();
    const completed = [
      exportTreasury ? 'treasury' : null,
      exportContributions ? 'contributions' : null,
    ].filter(Boolean).join(' and ');
    setStatus(`Forge Hammer exported ${completed}.`, 'done');
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  };

  const task = manualCapture ? startManualCapture() : run();
  task.catch(error => {
    gameHooks.restoreNameCapture?.();
    gameHooks.restoreClanLogModel?.();
    gameHooks.restoreBaseDispatcher?.();
    gameHooks.restoreDispatcher?.();
    setStatus(`Forge Hammer export stopped: ${error.message}`, 'error');
    console.error('[GoE data exporter]', {
      error,
      treasuryTriggerStarted: gameHooks.treasuryTriggerStarted,
      messageCenterTriggerStarted: gameHooks.messageCenterTriggerStarted,
      contributionTriggerStarted: gameHooks.contributionTriggerStarted,
      capturedClasses: Array.from(gameHooks.classes.keys()),
      capturedDispatchers: gameHooks.dispatchers.size,
    });
    console.error('[GoE data exporter] diagnostic ' + JSON.stringify({
      message: error.message,
      treasuryTriggerStarted: gameHooks.treasuryTriggerStarted,
      messageCenterTriggerStarted: gameHooks.messageCenterTriggerStarted,
      contributionTriggerStarted: gameHooks.contributionTriggerStarted,
      capturedClasses: Array.from(gameHooks.classes.keys()),
      capturedDispatchers: gameHooks.dispatchers.size,
    }));
  });
})();
