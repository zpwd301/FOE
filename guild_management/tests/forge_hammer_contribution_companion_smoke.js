'use strict';

const path = require('path');

const contributionEventType = 'ConversationWindowEvent/OPEN_GUILD_CONTRIBUTION';
const messageCenterEventType = 'ConversationWindowEvent/REQUEST_MESSAGE_CENTER';
const elements = new Map();
const requestHandlers = [];
const responseHandlers = [];
const requestedOffsets = [];
let exportedRows = null;
let nextRequestId = 900;

global.window = global;
window.location = {
  hash: '#forge-hammer-treasury-export=offline-contribution-smoke&treasury=0&contributions=1&contribution_cutoff=2026-08-16T09%3A00%3A00',
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
    exportedRows = this.Logs.length;
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

const pageFirstTimes = [
  '2026-08-16T10:00:00',
  '2026-08-16T09:30:00',
  '2026-08-16T08:50:00',
];

const createPageLogs = offset => {
  const page = offset / 10;
  const first = new Date(pageFirstTimes[page]);
  return Array.from({ length: 10 }, (_unused, index) => ({
    player: { player_id: 855340115, name: 'zpwd' },
    resource: 'fusion_reactors',
    amount: 100 + offset + index,
    action: 'Guild treasury donation',
    createdAt: new Date(first.getTime() - index * 60_000).toISOString(),
  }));
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
    responseData: { count: 100, logs: createPageLogs(offset) },
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
  if (exportedRows !== 30) {
    const status = elements.get('goe-forge-hammer-export-status');
    console.error(status?.textContent || `Exported ${exportedRows} rows; expected 30.`);
    process.exit(1);
  }
  if (JSON.stringify(requestedOffsets) !== JSON.stringify([0, 10, 20])) {
    console.error(`Unexpected page offsets: ${JSON.stringify(requestedOffsets)}`);
    process.exit(1);
  }
  console.log('Forge Hammer contribution smoke test passed with offsets 0, 10, 20.');
}, 1_500);
