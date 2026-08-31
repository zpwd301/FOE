'use strict';

const path = require('path');

const mode = process.argv[2] || 'overlap';
const contributionEventType = 'ConversationWindowEvent/OPEN_GUILD_CONTRIBUTION';
const messageCenterEventType = 'ConversationWindowEvent/REQUEST_MESSAGE_CENTER';
const elements = new Map();
const requestHandlers = [];
const responseHandlers = [];
const requestedOffsets = [];
let exportedMarkers = null;
let nextRequestId = 1200;

global.window = global;
window.location = {
  hash: '#forge-hammer-treasury-export=offline-overlap-smoke&treasury=0&contributions=1&contribution_cutoff=2026-08-16T09%3A00%3A00',
  pathname: '/game/index',
  search: '',
};
window.history = { replaceState() {} };
window.addEventListener = () => {};
global.document = {
  documentElement: {
    appendChild(element) {
      elements.set(element.id, element);
    },
  },
  createElement() {
    return { id: '', style: {}, textContent: '' };
  },
  getElementById(id) {
    return elements.get(id) || null;
  },
};
global.moment = () => ({ format: () => '2026-08-17' });
global.Settings = {
  GetSetting(name) {
    return name === 'ShowGuildTreasuryLogExport';
  },
};
global.Treasury = {
  Logs: [],
  Export() {
    exportedMarkers = this.Logs.map(log => log.marker);
  },
};

responseHandlers.push(data => {
  const logs = data.responseData.logs.map(log => ({
    ...log,
    createdAt: new Date(log.createdAt),
  }));
  Treasury.Logs = Treasury.Logs.concat(logs);
});

global.FH = {
  proxy: {
    addRequestHandler(_service, _method, handler) {
      requestHandlers.push(handler);
    },
    removeRequestHandler(_service, _method, handler) {
      const index = requestHandlers.indexOf(handler);
      if (index >= 0) requestHandlers.splice(index, 1);
    },
    addHandler(_service, _method, handler) {
      responseHandlers.push(handler);
    },
    removeHandler(_service, _method, handler) {
      const index = responseHandlers.indexOf(handler);
      if (index >= 0) responseHandlers.splice(index, 1);
    },
  },
};

require(path.resolve(__dirname, '../chrome/forge-hammer-treasury-exporter/export-treasury.js'));

const createLog = index => ({
  marker: `log-${index}`,
  player: { player_id: 855340115, name: 'zpwd' },
  resource: 'fusion_reactors',
  amount: 100 + index,
  action: 'Guild treasury donation',
  createdAt: new Date(new Date(2026, 7, 16, 10, 0).getTime() - index * 5 * 60_000).toISOString(),
});

const createPageLogs = offset => {
  if (offset === 0) return Array.from({ length: 10 }, (_unused, index) => createLog(index));
  if (offset === 10) {
    const start = mode === 'mismatch' ? 6 : 5;
    return Array.from({ length: 10 }, (_unused, index) => createLog(start + index));
  }
  return Array.from({ length: 10 }, (_unused, index) => createLog(15 + index));
};

let model;
const sendPage = offset => {
  requestedOffsets.push(offset);
  const request = {
    requestId: nextRequestId++,
    requestClass: 'ClanService',
    requestMethod: 'getTreasuryLogs',
    requestData: [10, offset, { __enum__: 'ResourceBagType', value: 'ClanMain' }],
  };
  requestHandlers.slice().forEach(handler => handler(request));
  const response = {
    requestId: request.requestId,
    requestClass: request.requestClass,
    requestMethod: request.requestMethod,
    responseData: {
      count: offset === 0 ? 100 : 105,
      logs: createPageLogs(offset),
    },
  };
  responseHandlers.slice().forEach(handler => handler(response, [request]));
  if (offset === 0) model.init(response.responseData, 0);
  else model.set_clanTreasuryLogsVO(response.responseData);
};

function BaseDispatcher() {
  this.eventTypes = new Set();
}
BaseDispatcher.__name__ = 'openfl.events.EventDispatcher';
BaseDispatcher.prototype.addEventListener = function (type) {
  this.eventTypes.add(type);
};
BaseDispatcher.prototype.hasEventListener = function (type) {
  return this.eventTypes.has(type);
};
BaseDispatcher.prototype.dispatchEvent = function (event) {
  if (event.type === contributionEventType) sendPage(0);
  return true;
};

function ModuleDispatcher() {
  BaseDispatcher.call(this);
}
ModuleDispatcher.__name__ = 'org.robotlegs.utilities.modular.base.ModuleEventDispatcher';
ModuleDispatcher.prototype = Object.create(BaseDispatcher.prototype);
ModuleDispatcher.prototype.constructor = ModuleDispatcher;

function ConversationWindowEvent(type) {
  this.type = type;
}
ConversationWindowEvent.__name__ =
  'de.innogames.strategycity.shared.event.ConversationWindowEvent';

function ClanTreasuryLogModel() {
  this.currentPage = 0;
}
ClanTreasuryLogModel.__name__ =
  'de.innogames.strategycity.main.model.ClanTreasuryLogModel';
ClanTreasuryLogModel.prototype.init = function (_data, page) {
  this.currentPage = page;
};
ClanTreasuryLogModel.prototype.set_currentPage = function (page) {
  this.currentPage = page;
  sendPage(page * 10);
};
ClanTreasuryLogModel.prototype.set_clanTreasuryLogsVO = function () {};

const moduleDispatcher = new ModuleDispatcher();
const contributionDispatcher = new BaseDispatcher();
model = new ClanTreasuryLogModel();
Promise.resolve().then(() => {
  moduleDispatcher.addEventListener(messageCenterEventType, () => {});
  contributionDispatcher.addEventListener(contributionEventType, () => {});
});

setTimeout(() => {
  const status = elements.get('goe-forge-hammer-export-status');
  if (mode === 'mismatch') {
    if (exportedMarkers !== null) {
      console.error('Ambiguous contribution overlap was exported instead of rejected.');
      process.exit(1);
    }
    if (!status?.textContent.includes('expected page-boundary overlap did not match')) {
      console.error(status?.textContent || 'Missing overlap-mismatch failure status.');
      process.exit(1);
    }
    console.log('Forge Hammer contribution overlap mismatch failed closed.');
    return;
  }

  const expectedMarkers = Array.from({ length: 25 }, (_unused, index) => `log-${index}`);
  if (JSON.stringify(exportedMarkers) !== JSON.stringify(expectedMarkers)) {
    console.error(
      status?.textContent ||
      `Exported ${JSON.stringify(exportedMarkers)}; expected ${JSON.stringify(expectedMarkers)}.`
    );
    process.exit(1);
  }
  if (JSON.stringify(requestedOffsets) !== JSON.stringify([0, 10, 20])) {
    console.error(`Unexpected page offsets: ${JSON.stringify(requestedOffsets)}`);
    process.exit(1);
  }
  console.log('Forge Hammer contribution overlap smoke test removed five proven rows.');
}, 1_500);
