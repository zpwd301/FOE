(() => {
  'use strict';

  const triggerKey = 'forge-hammer-treasury-export';
  const triggerStorageKey = '__goeForgeHammerDataExportTrigger';
  const triggerWindowPrefix = '__goe_forge_hammer_trigger__:';
  const expectedTreasuryGoods = 115;
  const directTriggerText = window.location.hash.replace(/^#/, '');
  const directTriggerParams = new URLSearchParams(directTriggerText);
  const liveDebugMode = directTriggerParams.get('foe_live_debug');
  const liveDebug = liveDebugMode === '1' || liveDebugMode === 'play_once';

  if (liveDebug) {
    const normalizedDebugText = value => String(value || '').replace(/\s+/g, ' ').trim();
    const safeUrl = value => {
      try {
        const parsed = new URL(value, window.location.href);
        return `${parsed.origin}${parsed.pathname}`;
      } catch (_error) {
        return null;
      }
    };
    const describeElement = element => {
      const rect = element.getBoundingClientRect?.();
      const style = window.getComputedStyle?.(element);
      const dataset = Object.fromEntries(
        Object.entries(element.dataset || {}).filter(([key]) => (
          /action|play|world|server/i.test(key)
        ))
      );
      return {
        tag: element.tagName?.toLowerCase() || null,
        text: normalizedDebugText(element.textContent).slice(0, 240),
        value: normalizedDebugText(element.value).slice(0, 240),
        ariaLabel: element.getAttribute?.('aria-label'),
        title: element.getAttribute?.('title'),
        type: element.getAttribute?.('type'),
        role: element.getAttribute?.('role'),
        id: element.id || null,
        className: normalizedDebugText(element.className).slice(0, 240),
        href: safeUrl(element.getAttribute?.('href')),
        dataset,
        disabled: Boolean(element.disabled),
        hidden: Boolean(element.hidden),
        visible: Boolean(
          rect && rect.width > 0 && rect.height > 0 &&
          style?.display !== 'none' && style?.visibility !== 'hidden'
        ),
        rect: rect ? {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        } : null,
      };
    };
    const collectControls = root => {
      const controls = [];
      const visitedRoots = new Set();
      const visit = currentRoot => {
        if (!currentRoot || visitedRoots.has(currentRoot)) return;
        visitedRoots.add(currentRoot);
        const candidates = currentRoot.querySelectorAll?.([
          'button',
          'a',
          'input[type="button"]',
          'input[type="submit"]',
          '[role="button"]',
          '[onclick]',
          '[data-action]',
          '[data-world-name]',
          '[data-world]',
          '[data-server]',
          '[class*="play" i]',
          '[id*="play" i]',
        ].join(',')) || [];
        for (const candidate of candidates) {
          controls.push(describeElement(candidate));
          if (candidate.shadowRoot) visit(candidate.shadowRoot);
          if (candidate.tagName === 'IFRAME') {
            try {
              visit(candidate.contentDocument);
            } catch (_error) {
              // Cross-origin frame metadata is reported separately below.
            }
          }
        }
        for (const element of currentRoot.querySelectorAll?.('*') || []) {
          if (element.shadowRoot) visit(element.shadowRoot);
        }
      };
      visit(root);
      return controls.slice(0, 1000);
    };
    const saveLiveDebugReport = () => {
      const report = {
        capturedAt: new Date().toISOString(),
        page: {
          url: `${window.location.origin}${window.location.pathname}`,
          title: document.title,
          readyState: document.readyState,
          viewport: { width: window.innerWidth, height: window.innerHeight },
        },
        frames: Array.from(document.querySelectorAll('iframe')).map(frame => ({
          src: safeUrl(frame.getAttribute('src')),
          title: frame.getAttribute('title'),
          visible: frame.getClientRects().length > 0,
        })),
        controls: collectControls(document),
      };
      const blob = new Blob([`${JSON.stringify(report, null, 2)}\n`], {
        type: 'application/json',
      });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `foe-live-debug-${Date.now()}.json`;
      link.hidden = true;
      document.documentElement.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      document.title = `FOE LIVE DEBUG: ${report.controls.length} controls captured`;
      console.info('[GoE live debug] Diagnostic-only report saved.', report);
    };
    const runLiveDebug = async () => {
      await new Promise(resolve => window.setTimeout(resolve, 5000));
      if (
        liveDebugMode === 'play_once' &&
        window.name !== '__goe_live_debug_play_clicked__'
      ) {
        const play = document.querySelector('#play_now_button');
        const rect = play?.getBoundingClientRect?.();
        if (play && !play.disabled && rect?.width > 0 && rect?.height > 0) {
          window.name = '__goe_live_debug_play_clicked__';
          play.click();
          await new Promise(resolve => window.setTimeout(resolve, 5000));
        }
      }
      saveLiveDebugReport();
    };
    void runLiveDebug();
    return;
  }
  const directTrigger = (
    directTriggerParams.get(triggerKey) || directTriggerParams.get('manual_capture') === '1'
  );

  const decodeWindowEnvelope = () => {
    if (!String(window.name || '').startsWith(triggerWindowPrefix)) return null;
    try {
      return JSON.parse(decodeURIComponent(window.name.slice(triggerWindowPrefix.length)));
    } catch (_error) {
      return null;
    }
  };
  const decodeSessionEnvelope = () => {
    try {
      const stored = window.sessionStorage?.getItem(triggerStorageKey);
      return stored ? JSON.parse(stored) : null;
    } catch (_error) {
      return null;
    }
  };

  const priorEnvelope = decodeWindowEnvelope() || decodeSessionEnvelope();
  const triggerEnvelope = directTrigger
    ? {
        params: directTriggerText,
        previousWindowName: priorEnvelope?.previousWindowName || (
          String(window.name || '').startsWith(triggerWindowPrefix) ? '' : String(window.name || '')
        ),
        steps: priorEnvelope?.params === directTriggerText ? priorEnvelope.steps || {} : {},
        diagnostics: priorEnvelope?.params === directTriggerText
          ? priorEnvelope.diagnostics || []
          : [],
      }
    : priorEnvelope;
  if (!triggerEnvelope?.params) return;

  const persistTriggerEnvelope = () => {
    const encoded = triggerWindowPrefix + encodeURIComponent(JSON.stringify(triggerEnvelope));
    window.name = encoded;
    try {
      window.sessionStorage?.setItem(triggerStorageKey, JSON.stringify(triggerEnvelope));
    } catch (_error) {
      // window.name carries the trigger across world-selection host changes.
    }
  };
  const clearPersistedTrigger = () => {
    triggerEnvelope.cleared = true;
    try {
      window.sessionStorage?.removeItem(triggerStorageKey);
    } catch (_error) {
      // Ignore storage restrictions; window.name is cleared below.
    }
    if (String(window.name || '').startsWith(triggerWindowPrefix)) {
      window.name = triggerEnvelope.previousWindowName || '';
    }
    const current = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    if (current.get(triggerKey) || current.get('manual_capture') === '1') {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    }
  };
  const markNavigationStep = step => {
    triggerEnvelope.steps ||= {};
    if (triggerEnvelope.steps[step]) {
      throw new Error(`The ${step} navigation action was already used; no retry was made.`);
    }
    triggerEnvelope.steps[step] = true;
    persistTriggerEnvelope();
  };
  persistTriggerEnvelope();

  const triggerParams = new URLSearchParams(triggerEnvelope.params);
  const manualCapture = triggerParams.get('manual_capture') === '1';
  if (!triggerParams.get(triggerKey) && !manualCapture) {
    clearPersistedTrigger();
    return;
  }

  const exportTreasury = !manualCapture && triggerParams.get('treasury') !== '0';
  const exportContributions = manualCapture || triggerParams.get('contributions') === '1';
  const contributionCutoffText = triggerParams.get('contribution_cutoff');
  const expectedWorldName = triggerParams.get('world_name') || 'Yorkton';
  const liveExportDebug = triggerParams.get('live_debug') === '1';
  const isGameClientPage = /^\/game\/index(?:\/|$)/.test(window.location.pathname);
  const diagnosticTrace = triggerEnvelope.diagnostics ||= [];
  const trace = (event, data = {}) => {
    if (!liveExportDebug) return;
    diagnosticTrace.push({
      at: new Date().toISOString(),
      event,
      ...data,
    });
    if (diagnosticTrace.length > 500) diagnosticTrace.shift();
    if (!isGameClientPage && !triggerEnvelope.cleared) persistTriggerEnvelope();
    console.info('[GoE live export debug]', event, data);
  };
  const runMarker = '__goeForgeHammerDataExportStarted';
  if (window[runMarker]) return;
  window[runMarker] = true;
  trace('companion-started', {
    page: `${window.location.origin}${window.location.pathname}`,
    exportTreasury,
    exportContributions,
    expectedWorldName,
  });

  const showClanEventName =
    'de.innogames.strategycity.shared.ui.window.clans.controller.ShowClanWindowCommand_Event';
  const windowEventName = 'de.innogames.strategycity.shared.event.WindowEvent';
  const conversationWindowEventName =
    'de.innogames.strategycity.shared.event.ConversationWindowEvent';
  const clanLogModelName =
    'de.innogames.strategycity.main.model.ClanTreasuryLogModel';
  const baseDispatcherName = 'openfl.events.EventDispatcher';
  const moduleDispatcherName = 'org.robotlegs.utilities.modular.base.ModuleEventDispatcher';
  const showClanEventType =
    'de.innogames.strategycity.shared.ui.window.clans.controller.ShowClanWindowCommand/EVENT_TYPE';
  const closeAllWindowsEventType = 'WindowEvent/CLOSE_ALL_WINDOW';
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
    closeAllWindowsStarted: false,
    messageCenterTriggerStarted: false,
    contributionTriggerStarted: false,
  };

  const saveDiagnosticReport = (result, message = null) => {
    if (!liveExportDebug) return;
    const report = {
      capturedAt: new Date().toISOString(),
      result,
      message,
      page: `${window.location.origin}${window.location.pathname}`,
      requestedExports: {
        treasury: exportTreasury,
        contributions: exportContributions,
      },
      navigationSteps: { ...(triggerEnvelope.steps || {}) },
      gameActions: {
        closeAllWindowsStarted: gameHooks.closeAllWindowsStarted,
        treasuryTriggerStarted: gameHooks.treasuryTriggerStarted,
        messageCenterTriggerStarted: gameHooks.messageCenterTriggerStarted,
        contributionTriggerStarted: gameHooks.contributionTriggerStarted,
      },
      capturedClasses: Array.from(gameHooks.classes.keys()),
      capturedDispatcherCount: gameHooks.dispatchers.size,
      trace: [...diagnosticTrace],
    };
    const blob = new Blob([`${JSON.stringify(report, null, 2)}\n`], {
      type: 'application/json',
    });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `foe-export-debug-${result}-${Date.now()}.json`;
    link.hidden = true;
    document.documentElement.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    console.info('[GoE live export debug] Report saved.', report);
  };
  if (liveExportDebug) {
    window.__goeForgeHammerLiveDebug = {
      trace: diagnosticTrace,
      saveReport: () => saveDiagnosticReport('manual'),
    };
  }

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
    trace('status', { message, state });
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

  const normalizedText = value => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const directActionSelector = [
    'button',
    'a',
    'input[type="button"]',
    'input[type="submit"]',
    '[role="button"]',
    '[data-world-name]',
    '[data-world]',
    '[data-server]',
  ].join(',');
  const interactiveSelector = [
    directActionSelector,
    'li',
    'span',
  ].join(',');
  const isUsableAction = element => {
    if (!element || element.hidden || element.disabled) return false;
    if (typeof element.getClientRects === 'function' && element.getClientRects().length === 0) {
      return false;
    }
    return typeof element.click === 'function';
  };
  const actionText = element => normalizedText([
    element.textContent,
    element.value,
    element.getAttribute?.('aria-label'),
    element.getAttribute?.('title'),
    element.getAttribute?.('data-world-name'),
    element.getAttribute?.('data-world'),
    element.getAttribute?.('data-server'),
  ].filter(Boolean).join(' '));
  const clickableAncestor = element => {
    if (element.matches?.(directActionSelector)) return element;
    return element.closest?.(directActionSelector)
      || element.querySelector?.(directActionSelector)
      || element;
  };
  const findAction = (labels, { prefix = false } = {}) => {
    const wanted = labels.map(normalizedText);
    for (const candidate of document.querySelectorAll?.(interactiveSelector) || []) {
      const text = actionText(candidate);
      const matches = wanted.some(label => text === label || (prefix && text.startsWith(`${label} `)));
      if (!matches) continue;
      const action = clickableAncestor(candidate);
      if (isUsableAction(action)) return action;
    }
    return null;
  };
  const clickNavigationAction = (step, element, status) => {
    trace('navigation-click', {
      step,
      tag: element.tagName?.toLowerCase() || null,
      id: element.id || null,
      label: actionText(element).slice(0, 120),
    });
    markNavigationStep(step);
    setStatus(status);
    element.click();
  };
  const enterConfiguredWorld = async () => {
    setStatus(`Waiting for Play or ${expectedWorldName} world selection…`);
    const firstAction = await waitUntil(() => {
      const world = findAction([expectedWorldName], { prefix: true });
      if (world) return { kind: 'world', element: world };
      const play = findAction(['Play', 'Play now']);
      return play ? { kind: 'play', element: play } : null;
    }, `Could not find Play or the ${expectedWorldName} world selector; no retry was made.`);

    if (firstAction.kind === 'world') {
      trace('landing-action-found', { kind: 'world' });
      clickNavigationAction(
        'world',
        firstAction.element,
        `Selecting ${expectedWorldName} once…`
      );
      return;
    }

    trace('landing-action-found', { kind: 'play' });
    clickNavigationAction('play', firstAction.element, 'Opening world selection once…');
    const world = await waitUntil(
      () => findAction([expectedWorldName], { prefix: true }),
      `Play opened, but the ${expectedWorldName} world selector did not appear; no retry was made.`
    );
    clickNavigationAction('world', world, `Selecting ${expectedWorldName} once…`);
  };

  // ForgeHX keeps its class registry private, but assigns each Haxe class its
  // stable, fully-qualified __name__. Capture only the classes required to
  // dispatch the same events and page changes as the game UI.
  const installGameClientHooks = () => {
    const originalNameDescriptor = Object.getOwnPropertyDescriptor(Function.prototype, '__name__');
    const wantedNames = new Set([moduleDispatcherName]);
    if (exportContributions) wantedNames.add(baseDispatcherName);
    if (exportTreasury) {
      wantedNames.add(windowEventName);
      wantedNames.add(showClanEventName);
    }
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
      trace('game-hooks-armed', {
        capturedClasses: Array.from(gameHooks.classes.keys()),
      });
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
            trace('game-class-captured', { name: value });
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
    trace('treasury-action-dispatch', { selectedTabId: 'treasury' });
    dispatcher.dispatchEvent(new ShowClanWindowEvent(null, 'treasury'));
  };

  const closeAllGameWindowsOnce = dispatcher => {
    if (gameHooks.closeAllWindowsStarted) {
      throw new Error('The close-all-windows action was already used; no retry was made.');
    }
    gameHooks.closeAllWindowsStarted = true;
    const WindowEvent = gameHooks.classes.get(windowEventName);
    if (typeof WindowEvent !== 'function') {
      throw new Error('The game close-window event class is unavailable; Treasury was not opened.');
    }
    trace('close-all-windows-dispatch', { eventType: closeAllWindowsEventType });
    dispatcher.dispatchEvent(new WindowEvent(closeAllWindowsEventType));
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
    trace('contribution-action-dispatch', { eventType: contributionEventType });
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
    trace('message-center-action-dispatch', { eventType: messageCenterEventType });
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
      trace('treasury-request', {
        requestId: request?.requestId ?? null,
        bagType: bagType || null,
      });
    };
    const responseHandler = data => {
      if (!outgoingRequest || data?.requestId !== outgoingRequest.requestId) return;
      response = data;
      trace('treasury-response', {
        requestId: data.requestId,
        hasResources: Boolean(responseResources(data)),
      });
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
      trace('contribution-page-request', {
        requestId: request.requestId,
        offset,
        limit,
      });
    };
    const responseHandler = data => {
      if (!activeRequest || data?.requestId !== activeRequest.requestId) return;
      trace('contribution-page-response', {
        requestId: data.requestId,
        offset: activeRequest?.requestData?.[1] ?? null,
        rowCount: Array.isArray(data?.responseData?.logs)
          ? data.responseData.logs.length
          : null,
        totalCount: data?.responseData?.count ?? null,
      });
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
    const windowDispatcher = await waitUntil(
      () => findDispatcher(closeAllWindowsEventType),
      'The game client did not expose its close-window action; Treasury was not opened.'
    );
    setStatus('Closing existing game windows once before opening Treasury…');
    closeAllGameWindowsOnce(windowDispatcher);
    await sleep(750);
    trace('close-all-windows-settled', { settleMilliseconds: 750 });
    const dispatcher = await waitUntil(
      () => findDispatcher(showClanEventType),
      'The game client did not expose its Treasury action before the timeout; no request was sent.'
    );
    trace('treasury-dispatcher-ready');
    await IndexDB.getDB();
    trace('forge-hammer-database-ready');
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
      trace('treasury-storage-verified', {
        requestId: observed.response.requestId,
        currentHour,
        currentDay,
      });
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
    if (!Array.isArray(series) || series.length !== expectedTreasuryGoods) {
      throw new Error(
        `Forge Hammer prepared ${series?.length || 0} goods; expected ${expectedTreasuryGoods}.`
      );
    }
    const timestamps = series.flatMap(item => item.data.map(point => Number(point[0])));
    if (Math.max(...timestamps) !== Number(moment().startOf('day'))) {
      throw new Error('Forge Hammer daily history does not contain today\'s stored snapshot.');
    }
    trace('treasury-export-invoked', {
      goods: series.length,
      latestTimestamp: Math.max(...timestamps),
    });
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
    trace('contribution-dispatcher-ready');
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
    trace('contribution-pagination-complete', {
      pages: page + 1,
      rows: accumulatedRows,
      stopReason,
    });
    trace('contribution-export-invoked', { rows: accumulatedRows });
    Treasury.Export();
  };

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
    trace('forge-hammer-ready', {
      capturedClasses: Array.from(gameHooks.classes.keys()),
      capturedDispatcherCount: gameHooks.dispatchers.size,
    });
    // Reaching an initialized game client makes the landing-page trigger
    // single-use even if a later export step fails.
    clearPersistedTrigger();

    if (exportTreasury) await exportStoredTreasury();
    if (exportContributions) await exportContributionLogs();

    gameHooks.restoreClanLogModel?.();
    gameHooks.restoreBaseDispatcher?.();
    gameHooks.restoreDispatcher?.();
    const completed = [
      exportTreasury ? 'treasury' : null,
      exportContributions ? 'contributions' : null,
    ].filter(Boolean).join(' and ');
    trace('workflow-complete', { completed });
    saveDiagnosticReport('complete');
    setStatus(
      liveExportDebug
        ? `Forge Hammer exported ${completed}. Live debug is waiting for manual input.`
        : `Forge Hammer exported ${completed}.`,
      'done'
    );
  };

  if (isGameClientPage) installGameClientHooks();
  const task = isGameClientPage
    ? (manualCapture ? startManualCapture() : run())
    : enterConfiguredWorld();
  task.catch(error => {
    clearPersistedTrigger();
    gameHooks.restoreNameCapture?.();
    gameHooks.restoreClanLogModel?.();
    gameHooks.restoreBaseDispatcher?.();
    gameHooks.restoreDispatcher?.();
    trace('workflow-error', { message: error.message });
    saveDiagnosticReport('error', error.message);
    setStatus(`Forge Hammer export stopped: ${error.message}`, 'error');
    console.error('[GoE data exporter]', {
      error,
      closeAllWindowsStarted: gameHooks.closeAllWindowsStarted,
      treasuryTriggerStarted: gameHooks.treasuryTriggerStarted,
      messageCenterTriggerStarted: gameHooks.messageCenterTriggerStarted,
      contributionTriggerStarted: gameHooks.contributionTriggerStarted,
      capturedClasses: Array.from(gameHooks.classes.keys()),
      capturedDispatchers: gameHooks.dispatchers.size,
    });
    console.error('[GoE data exporter] diagnostic ' + JSON.stringify({
      message: error.message,
      closeAllWindowsStarted: gameHooks.closeAllWindowsStarted,
      treasuryTriggerStarted: gameHooks.treasuryTriggerStarted,
      messageCenterTriggerStarted: gameHooks.messageCenterTriggerStarted,
      contributionTriggerStarted: gameHooks.contributionTriggerStarted,
      capturedClasses: Array.from(gameHooks.classes.keys()),
      capturedDispatchers: gameHooks.dispatchers.size,
    }));
  });
})();
