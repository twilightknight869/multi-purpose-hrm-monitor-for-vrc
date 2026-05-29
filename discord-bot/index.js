require('dotenv').config();
const { Client, GatewayIntentBits, EmbedBuilder } = require('discord.js');
const { startApi } = require('./api');
const db = require('./database');

// ── Config ────────────────────────────────────────────────────────
const ADMIN_ROLE_ID = process.env.ADMIN_ROLE_ID || '';   // Role allowed to use admin commands
const LOG_CHANNEL   = process.env.LOG_CHANNEL_ID || '';  // Channel for key activity logs
const CASHAPP_TAG   = process.env.CASHAPP_TAG || '$YourTag';
const PRICE         = process.env.PRICE || '$5.00/month';

// ── Discord client ────────────────────────────────────────────────
const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.DirectMessages],
});

// ── Helpers ───────────────────────────────────────────────────────
function isAdmin(member) {
  if (!member) return false;
  if (member.permissions.has('Administrator')) return true;
  if (ADMIN_ROLE_ID && member.roles.cache.has(ADMIN_ROLE_ID)) return true;
  return false;
}

async function logAction(guild, embed) {
  if (!LOG_CHANNEL) return;
  try {
    const ch = await guild.channels.fetch(LOG_CHANNEL);
    if (ch?.isTextBased()) ch.send({ embeds: [embed] });
  } catch { /* log channel not found — ignore */ }
}

function keyEmbed(key, discordTag, note, expiresAt) {
  const exp = expiresAt ? `<t:${Math.floor(expiresAt / 1000)}:D>` : 'Never';
  return new EmbedBuilder()
    .setColor(0xe03535)
    .setTitle('♥  HRM Monitor — Premium License')
    .addFields(
      { name: 'License Key',  value: `\`${key}\`` },
      { name: 'User',         value: discordTag, inline: true },
      { name: 'Expires',      value: exp,        inline: true },
      { name: 'Note',         value: note || '—', inline: true },
    )
    .setFooter({ text: 'Enter this key in HRM Monitor → Settings → License' })
    .setTimestamp();
}

// ── Slash command handler ─────────────────────────────────────────
client.on('interactionCreate', async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const { commandName, guild, member } = interaction;

  // ──────────────────── ADMIN COMMANDS ────────────────────────────
  if (['addkey', 'revokekey', 'listkeys', 'checkkey', 'botstats'].includes(commandName)) {
    if (!isAdmin(member)) {
      return interaction.reply({ content: '❌ Admin only.', ephemeral: true });
    }
  }

  // /addkey
  if (commandName === 'addkey') {
    const target  = interaction.options.getUser('user');
    const days    = interaction.options.getInteger('days') ?? null;
    const note    = interaction.options.getString('note') ?? null;

    // Check if user already has a key
    const existing = db.getKeyByDiscordId(target.id);
    if (existing) {
      return interaction.reply({
        content: `⚠️ ${target.tag} already has an active key: \`${existing.key}\`\nRevoke it first with \`/revokekey\`.`,
        ephemeral: true
      });
    }

    const key = db.createKey(target.id, target.tag, note, days);

    // DM the key to the user
    try {
      const embed = keyEmbed(key, target.tag, note, days ? Date.now() + days * 86400000 : null);
      await target.send({ content: `🎉 Your HRM Monitor Premium license is ready!`, embeds: [embed] });
    } catch {
      await interaction.reply({
        content: `✅ Key created: \`${key}\`\n⚠️ Could not DM ${target.tag} — they may have DMs disabled. Send the key manually.`,
        ephemeral: true
      });
      await logAction(guild, keyEmbed(key, target.tag, note, null));
      return;
    }

    await interaction.reply({
      content: `✅ Premium key issued to ${target.tag} and DMed to them.`,
      ephemeral: true
    });

    await logAction(guild, keyEmbed(key, target.tag, note, null)
      .setTitle('♥  Key Issued')
      .addFields({ name: 'Issued By', value: interaction.user.tag }));
    return;
  }

  // /revokekey
  if (commandName === 'revokekey') {
    const target = interaction.options.getUser('user');
    const ok = db.revokeKey(target.id);

    if (!ok) {
      return interaction.reply({ content: `⚠️ No active key found for ${target.tag}.`, ephemeral: true });
    }

    await interaction.reply({ content: `✅ Key revoked for ${target.tag}.`, ephemeral: true });

    await logAction(guild, new EmbedBuilder()
      .setColor(0xff4444)
      .setTitle('🔑 Key Revoked')
      .addFields(
        { name: 'User',       value: target.tag },
        { name: 'Revoked By', value: interaction.user.tag },
      )
      .setTimestamp());
    return;
  }

  // /listkeys
  if (commandName === 'listkeys') {
    const keys = db.listKeys(15);
    if (!keys.length) return interaction.reply({ content: 'No keys found.', ephemeral: true });

    const lines = keys.map(k =>
      `\`${k.key}\`  •  **${k.discord_tag}**  •  ${k.active ? '✅' : '❌'}  •  ${k.note ?? '—'}`
    ).join('\n');

    await interaction.reply({ content: `**Recent license keys:**\n${lines}`, ephemeral: true });
    return;
  }

  // /checkkey
  if (commandName === 'checkkey') {
    const key = interaction.options.getString('key');
    const license = db.getKeyByKey(key);

    if (!license) return interaction.reply({ content: '❌ Key not found.', ephemeral: true });

    const status  = license.active ? '✅ Active' : '❌ Revoked';
    const exp     = license.expires_at ? `<t:${Math.floor(license.expires_at / 1000)}:D>` : 'Never';

    await interaction.reply({
      content: `**Key:** \`${license.key}\`\n**User:** ${license.discord_tag}\n**Status:** ${status}\n**Expires:** ${exp}\n**Note:** ${license.note ?? '—'}`,
      ephemeral: true
    });
    return;
  }

  // /botstats
  if (commandName === 'botstats') {
    const s = db.getStats();
    await interaction.reply({
      content: `**HRM License Stats**\nTotal keys: **${s.total}**\nActive keys: **${s.active}**\nTotal verifications: **${s.checks}**`,
      ephemeral: true
    });
    return;
  }

  // ──────────────────── USER COMMANDS ─────────────────────────────

  // /mykey
  if (commandName === 'mykey') {
    const license = db.getKeyByDiscordId(interaction.user.id);

    if (!license) {
      return interaction.reply({
        embeds: [new EmbedBuilder()
          .setColor(0xe03535)
          .setTitle('♥  HRM Monitor Premium')
          .setDescription(`You don't have a license yet.\n\n**To get one:**\n1. Send **${PRICE}** to CashApp **${CASHAPP_TAG}**\n2. DM this bot or post in the support channel with your CashApp username and payment screenshot\n3. An admin will issue your key within 24 hours`)
          .setFooter({ text: 'HRM Monitor by CRIMSON' })
        ],
        ephemeral: true
      });
    }

    // DM them the key
    try {
      const exp = license.expires_at ? `<t:${Math.floor(license.expires_at / 1000)}:D>` : 'Never';
      await interaction.user.send({
        embeds: [keyEmbed(license.key, license.discord_tag, license.note, license.expires_at)]
      });
      await interaction.reply({ content: '✅ Your license key has been sent to your DMs!', ephemeral: true });
    } catch {
      await interaction.reply({
        content: `Your key is: \`${license.key}\`\n*(Enable DMs to receive it privately next time)*`,
        ephemeral: true
      });
    }
    return;
  }
});

// ── Ready ─────────────────────────────────────────────────────────
client.once('ready', () => {
  console.log(`[Bot] Logged in as ${client.user.tag}`);
  client.user.setActivity('HRM Monitor licenses', { type: 3 /* Watching */ });
});

// ── Start ─────────────────────────────────────────────────────────
client.login(process.env.DISCORD_TOKEN);
startApi(process.env.PORT || 3000);
