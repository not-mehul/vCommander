// Delete a leftover API key by name (see api_key.js).
module.exports = (s, ui, name) => require('./api_key').remove(s, ui, name);
