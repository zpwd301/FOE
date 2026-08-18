'use strict';

const path = require('path');

const showEventType =
  'de.innogames.strategycity.shared.ui.window.clans.controller.ShowClanWindowCommand/EVENT_TYPE';
const closeAllWindowsEventType = 'WindowEvent/CLOSE_ALL_WINDOW';
const resources = { stone: 123, lumber: 456 };
const elements = new Map();
let storedHourly = null;
let storedDaily = null;
let exported = false;
let requestCount = 0;

global.window = global;
window.location = {
  hash: '#forge-hammer-treasury-export=offline-smoke-test',
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

const startOf = unit => {
  const value = new Date();
  if (unit === 'day') value.setHours(0, 0, 0, 0);
  if (unit === 'hour') value.setMinutes(0, 0, 0);
  return {
    toDate: () => new Date(value),
    valueOf: () => value.getTime(),
  };
};

global.moment = () => ({
  startOf,
  format() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${month}-${day}`;
  },
});

const requestHandlers = [];
const responseHandlers = [data => {
  const storedResources = data.responseData.resources.resources;
  Promise.resolve().then(() => {
    storedHourly = { resources: { ...storedResources } };
    storedDaily = { resources: { ...storedResources } };
  });
}];

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

global.IndexDB = {
  async getDB() {},
  db: {
    statsTreasureClanH: { async get() { return storedHourly; } },
    statsTreasureClanD: { async get() { return storedDaily; } },
  },
};

global.Stats = {
  PlayableEras: ['bronzeAge'],
  state: {},
  async createTreasureSeries() {
    const today = Number(startOf('day'));
    return {
      series: Array.from({ length: 110 }, (_unused, index) => ({
        data: [[today, index]],
      })),
    };
  },
  exportCSV(series, filename) {
    if (series.length !== 110 || !/^stats-\d{4}-\d{2}-\d{2}\.csv$/.test(filename)) {
      throw new Error('Unexpected Forge Hammer export arguments.');
    }
    exported = true;
  },
};

require(path.resolve(__dirname, '../chrome/forge-hammer-treasury-exporter/export-treasury.js'));

function BaseDispatcher() {}
BaseDispatcher.prototype.addEventListener = function () {};
BaseDispatcher.prototype.hasEventListener = function (type) {
  return type === showEventType || type === closeAllWindowsEventType;
};
BaseDispatcher.prototype.dispatchEvent = function (event) {
  if (event.type === closeAllWindowsEventType) return true;
  if (event.type !== showEventType || event.selectedTabId !== 'treasury') return true;
  requestCount += 1;
  const request = {
    requestId: 731,
    requestClass: 'ClanService',
    requestMethod: 'getTreasuryBag',
    requestData: [{ __enum__: 'ResourceBagType', value: 'ClanMain' }],
  };
  requestHandlers.slice().forEach(handler => handler(request));
  const response = {
    requestId: request.requestId,
    requestClass: request.requestClass,
    requestMethod: request.requestMethod,
    responseData: { resources: { resources } },
  };
  responseHandlers.slice().forEach(handler => handler(response, [request]));
  return true;
};

function ModuleDispatcher() {}
ModuleDispatcher.__name__ = 'org.robotlegs.utilities.modular.base.ModuleEventDispatcher';
ModuleDispatcher.prototype = Object.create(BaseDispatcher.prototype);
ModuleDispatcher.prototype.constructor = ModuleDispatcher;

function WindowEvent(type) {
  this.type = type;
}
WindowEvent.__name__ = 'de.innogames.strategycity.shared.event.WindowEvent';

function ShowClanWindowEvent(clanId, selectedTabId) {
  this.type = showEventType;
  this.clanId = clanId;
  this.selectedTabId = selectedTabId;
}
ShowClanWindowEvent.__name__ =
  'de.innogames.strategycity.shared.ui.window.clans.controller.ShowClanWindowCommand_Event';

const dispatcher = new ModuleDispatcher();
Promise.resolve().then(() => dispatcher.addEventListener(showEventType, () => {}));

setTimeout(() => {
  if (!exported) {
    const status = elements.get('goe-forge-hammer-export-status');
    console.error(status?.textContent || 'Companion did not finish the offline smoke test.');
    process.exit(1);
  }
  if (requestCount !== 1) {
    console.error(`Companion triggered ${requestCount} requests; expected exactly one.`);
    process.exit(1);
  }
  console.log('Forge Hammer companion offline smoke test passed with one request.');
}, 1_000);
