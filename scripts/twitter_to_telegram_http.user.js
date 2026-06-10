// ==UserScript==
// @name         Twitter/X 推文媒体发送到 Telegram
// @namespace    http://tampermonkey.net/
// @version      2.0
// @description  为每个 Twitter/X 推文添加按钮，通过机器人后端 HTTP 服务下载并发送媒体
// @author       You
// @match        https://twitter.com/*
// @match        https://x.com/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_xmlhttpRequest
// @connect      *
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    let SUBMIT_ENDPOINT = GM_getValue('tg_submit_endpoint', 'http://127.0.0.1:8787/submit');
    let TELEGRAM_CHAT_ID = GM_getValue('telegram_chat_id', '');
    let SUBMIT_SECRET = GM_getValue('tg_submit_secret', '');

    function checkConfig() {
        if (!SUBMIT_ENDPOINT || !TELEGRAM_CHAT_ID || !SUBMIT_SECRET) {
            const endpoint = prompt('请输入机器人后端提交地址:', SUBMIT_ENDPOINT || 'http://127.0.0.1:8787/submit');
            const chatId = prompt('请输入 Telegram Chat ID:', TELEGRAM_CHAT_ID);
            const secret = prompt('请输入 HTTP_SUBMIT_SECRET:', SUBMIT_SECRET);

            if (!endpoint || !chatId || !secret) {
                showNotification('需要设置提交地址、Chat ID 和 Secret', 'error');
                return false;
            }

            SUBMIT_ENDPOINT = endpoint.trim();
            TELEGRAM_CHAT_ID = chatId.trim();
            SUBMIT_SECRET = secret.trim();
            GM_setValue('tg_submit_endpoint', SUBMIT_ENDPOINT);
            GM_setValue('telegram_chat_id', TELEGRAM_CHAT_ID);
            GM_setValue('tg_submit_secret', SUBMIT_SECRET);
        }
        return true;
    }

    function submitTweet(tweetUrl) {
        if (!checkConfig()) return;

        GM_xmlhttpRequest({
            method: 'POST',
            url: SUBMIT_ENDPOINT,
            headers: {
                'Content-Type': 'application/json',
                'X-Submit-Secret': SUBMIT_SECRET,
            },
            data: JSON.stringify({
                chat_id: TELEGRAM_CHAT_ID,
                url: tweetUrl,
            }),
            onload: function (response) {
                if (response.status >= 200 && response.status < 300) {
                    showNotification('已提交，机器人正在处理', 'success');
                    return;
                }
                console.error('提交失败:', response.status, response.responseText);
                showNotification('提交失败，请检查后端配置', 'error');
            },
            onerror: function (error) {
                console.error('网络错误:', error);
                showNotification('无法连接机器人后端', 'error');
            },
        });
    }

    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'success' ? '#2e7d32' : type === 'error' ? '#c62828' : '#1565c0'};
            color: white;
            border-radius: 6px;
            z-index: 100000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.25);
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 3000);
    }

    function getTweetUrl(tweetElement) {
        const timeLink = tweetElement.querySelector('time')?.closest('a');
        if (timeLink && timeLink.href) {
            return normalizeTweetUrl(timeLink.href);
        }

        const statusLinks = tweetElement.querySelectorAll('a[href*="/status/"]');
        if (statusLinks.length > 0) {
            return normalizeTweetUrl(statusLinks[0].href);
        }

        return null;
    }

    function normalizeTweetUrl(url) {
        try {
            const parsed = new URL(url);
            parsed.search = '';
            parsed.hash = '';
            return parsed.toString();
        } catch {
            return url;
        }
    }

    function createPushButton(tweetElement) {
        const button = document.createElement('button');
        button.textContent = 'TG';
        button.title = '发送推文媒体到 Telegram';
        button.style.cssText = `
            background: #1d9bf0;
            border: none;
            border-radius: 999px;
            min-width: 34px;
            height: 28px;
            color: white;
            cursor: pointer;
            font-size: 12px;
            font-weight: 700;
            margin-left: 8px;
            padding: 0 9px;
        `;

        button.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();

            const tweetUrl = getTweetUrl(tweetElement);
            if (!tweetUrl) {
                showNotification('无法获取推文链接', 'error');
                return;
            }
            submitTweet(tweetUrl);
        });

        return button;
    }

    function addPushButtonToTweet(tweetElement) {
        if (tweetElement.querySelector('.telegram-http-push-button')) return;

        const actionBar = tweetElement.querySelector('[role="group"]');
        if (!actionBar) return;

        const pushButton = createPushButton(tweetElement);
        pushButton.classList.add('telegram-http-push-button');
        actionBar.appendChild(pushButton);
    }

    function processTweets() {
        document.querySelectorAll('[data-testid="tweet"]').forEach(addPushButtonToTweet);
    }

    function observeDOMChanges() {
        const observer = new MutationObserver(function (mutations) {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType !== 1) continue;
                    if (
                        node.matches?.('[data-testid="tweet"]') ||
                        node.querySelector?.('[data-testid="tweet"]')
                    ) {
                        setTimeout(processTweets, 100);
                        return;
                    }
                }
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    function addSettingsButton() {
        const settingsButton = document.createElement('button');
        settingsButton.textContent = 'TG 设置';
        settingsButton.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #1d9bf0;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 999px;
            cursor: pointer;
            z-index: 99999;
            font-size: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.25);
        `;

        settingsButton.addEventListener('click', function () {
            const endpoint = prompt('机器人后端提交地址:', SUBMIT_ENDPOINT);
            const chatId = prompt('Telegram Chat ID:', TELEGRAM_CHAT_ID);
            const secret = prompt('HTTP_SUBMIT_SECRET:', SUBMIT_SECRET);

            if (!endpoint || !chatId || !secret) return;
            SUBMIT_ENDPOINT = endpoint.trim();
            TELEGRAM_CHAT_ID = chatId.trim();
            SUBMIT_SECRET = secret.trim();
            GM_setValue('tg_submit_endpoint', SUBMIT_ENDPOINT);
            GM_setValue('telegram_chat_id', TELEGRAM_CHAT_ID);
            GM_setValue('tg_submit_secret', SUBMIT_SECRET);
            showNotification('设置已保存', 'success');
        });

        document.body.appendChild(settingsButton);
    }

    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
            return;
        }

        setTimeout(processTweets, 1000);
        observeDOMChanges();
        setTimeout(addSettingsButton, 2000);
        console.log('Twitter/X 到 Telegram HTTP 提交脚本已启动');
    }

    init();
})();
