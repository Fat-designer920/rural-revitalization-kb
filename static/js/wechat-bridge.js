/**
 * wechat-bridge.js — 微信JSSDK轻量封装(ES5兼容)
 * 依赖: https://res.wx.qq.com/open/js/jweixin-1.6.0.js
 * 使用前需Flask后端提供wx.config签名
 */
var WechatBridge = {
  _ready: false,
  _config: null,

  /** 初始化: 从后端获取签名后调用wx.config */
  init: function(configUrl, callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', configUrl, true);
    xhr.onload = function() {
      if (xhr.status === 200) {
        var cfg = JSON.parse(xhr.responseText);
        WechatBridge._config = cfg;
        wx.config({
          debug: false,
          appId: cfg.appId,
          timestamp: cfg.timestamp,
          nonceStr: cfg.nonceStr,
          signature: cfg.signature,
          jsApiList: ['updateAppMessageShareData','updateTimelineShareData',
                      'startRecord','stopRecord','translateVoice',
                      'getLocation','chooseImage']
        });
        wx.ready(function() { WechatBridge._ready = true; if(callback) callback(true); });
        wx.error(function() { if(callback) callback(false); });
      }
    };
    xhr.send();
  },

  /** 分享给微信好友 */
  shareToFriend: function(title, desc, link, imgUrl) {
    if (!WechatBridge._ready) return;
    wx.updateAppMessageShareData({
      title: title, desc: desc, link: link, imgUrl: imgUrl || '',
      success: function() {}
    });
  },

  /** 分享到朋友圈 */
  shareToTimeline: function(title, link, imgUrl) {
    if (!WechatBridge._ready) return;
    wx.updateTimelineShareData({
      title: title, link: link, imgUrl: imgUrl || '',
      success: function() {}
    });
  },

  /** 语音识别(微信原生) */
  startVoice: function(callback) {
    if (!WechatBridge._ready) { if(callback) callback(null,'微信未就绪'); return; }
    wx.startRecord();
    wx.stopRecord({
      success: function(res) {
        wx.translateVoice({
          localId: res.localId,
          isShowProgressTips: 1,
          success: function(r) { if(callback) callback(r.translateResult,null); },
          fail: function(e) { if(callback) callback(null,e.errMsg); }
        });
      },
      fail: function(e) { if(callback) callback(null,e.errMsg); }
    });
  },

  /** 获取位置 */
  getLocation: function(callback) {
    if (!WechatBridge._ready) { if(callback) callback(null,'微信未就绪'); return; }
    wx.getLocation({
      type: 'wgs84',
      success: function(res) { if(callback) callback(res,null); },
      fail: function(e) { if(callback) callback(null,e.errMsg); }
    });
  },

  /** 检查是否在微信中 */
  isWechat: function() {
    return /micromessenger/i.test(navigator.userAgent);
  }
};
