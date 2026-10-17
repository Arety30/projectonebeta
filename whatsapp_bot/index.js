const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const fs = require('fs');

const client = new Client({
    authStrategy: new LocalAuth()
});

client.on('qr', (qr) => {
    qrcode.generate(qr, {small: true});
    console.log('QR RECEIVED - Scan this with your phone!');
});

client.on('ready', () => {
    console.log('Client is ready!');
});

client.on('message', async (msg) => {
    if (msg.hasMedia) {
        const media = await msg.downloadMedia();
        const buffer = Buffer.from(media.data, 'base64');
        
        // Save audio for local processing
        fs.writeFileSync('incoming.ogg', buffer);
        
        // Trigger our Python AI backend (via internal request)
        // Note: We need a small HTTP wrapper to pass this file to your Python STT
        try {
            const formData = new FormData();
            // ... logic to send to your Flask server ...
            console.log('Media received and saved.');
            msg.reply('I am processing your voice note...');
        } catch (err) {
            console.error(err);
        }
    }
});

client.initialize();
