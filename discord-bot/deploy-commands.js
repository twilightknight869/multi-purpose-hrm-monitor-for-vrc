// Run this ONCE after changing slash commands:  node deploy-commands.js
require('dotenv').config();
const { REST, Routes, SlashCommandBuilder } = require('discord.js');

const commands = [
  // ── Admin commands ─────────────────────────────────────────────
  new SlashCommandBuilder()
    .setName('addkey')
    .setDescription('[ADMIN] Issue a premium license key to a user')
    .addUserOption(o => o.setName('user').setDescription('Discord user').setRequired(true))
    .addIntegerOption(o => o.setName('days').setDescription('Expires in N days (leave blank = never)'))
    .addStringOption(o => o.setName('note').setDescription('Payment note (e.g. CashApp $12.00)')),

  new SlashCommandBuilder()
    .setName('revokekey')
    .setDescription('[ADMIN] Revoke a user\'s license key')
    .addUserOption(o => o.setName('user').setDescription('Discord user').setRequired(true)),

  new SlashCommandBuilder()
    .setName('listkeys')
    .setDescription('[ADMIN] List recent license keys'),

  new SlashCommandBuilder()
    .setName('checkkey')
    .setDescription('[ADMIN] Check who owns a key')
    .addStringOption(o => o.setName('key').setDescription('License key').setRequired(true)),

  new SlashCommandBuilder()
    .setName('botstats')
    .setDescription('[ADMIN] Show license server stats'),

  // ── User commands ──────────────────────────────────────────────
  new SlashCommandBuilder()
    .setName('mykey')
    .setDescription('Get your HRM Monitor license key (sent as DM)'),
].map(cmd => cmd.toJSON());

const rest = new REST().setToken(process.env.DISCORD_TOKEN);

(async () => {
  console.log('Deploying slash commands...');
  await rest.put(
    Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.GUILD_ID),
    { body: commands }
  );
  console.log('Done!');
})();
