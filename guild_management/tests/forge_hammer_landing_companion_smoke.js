'use strict';

const path = require('path');

const elements = new Map();
const storage = new Map();
let playClicks = 0;
let worldClicks = 0;
let worldVisible = false;

const action = (text, click, value = '') => ({
  textContent: text,
  value,
  hidden: false,
  disabled: false,
  click,
  closest() { return this; },
  getAttribute() { return null; },
  getClientRects() { return [1]; },
});
const play = action('', () => {
  playClicks += 1;
  worldVisible = true;
}, 'Play');
const yorkton = action('Yorkton', () => {
  worldClicks += 1;
});

global.window = global;
window.name = '';
window.location = {
  hash: '#forge-hammer-treasury-export=landing-smoke&treasury=1&contributions=1&world_name=Yorkton',
  pathname: '/page/',
  search: '',
};
window.history = { replaceState() {} };
window.addEventListener = () => {};
window.sessionStorage = {
  getItem(key) { return storage.get(key) || null; },
  setItem(key, value) { storage.set(key, value); },
  removeItem(key) { storage.delete(key); },
};
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
  querySelectorAll() {
    return worldVisible ? [play, yorkton] : [play];
  },
};

require(path.resolve(__dirname, '../chrome/forge-hammer-treasury-exporter/export-treasury.js'));

setTimeout(() => {
  if (playClicks !== 1 || worldClicks !== 1) {
    console.error(`Landing flow clicked Play ${playClicks} and Yorkton ${worldClicks} times.`);
    process.exit(1);
  }
  if (!window.name.startsWith('__goe_forge_hammer_trigger__:')) {
    console.error('Landing flow did not preserve the trigger across navigation.');
    process.exit(1);
  }
  console.log('Forge Hammer landing flow selected Play and Yorkton exactly once.');
}, 100);
