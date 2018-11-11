require('../logo.png');
import '../styles/index.scss';
var Cookies = require('js-cookie');

window.tables = [];

function csrfSafeMethod(method) {
  // these HTTP methods do not require CSRF protection
  return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

$(document).ready(function () {

    $.ajaxSetup({
      beforeSend: function(xhr, settings) {
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
          var csrftoken = Cookies.get('csrftoken');
          xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
      }
    });

    $("#keygen").click(function(){
      chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXTZabcdefghiklmnopqrstuvwxyz'.split('');
      key = _.sample(chars, 16).join("");
      var saveData = $.ajax({
        type: 'POST',
        url: $('#dashboard_url').val(),
        data: {'apikey': key},
        dataType: "text",
        success: function(data, textStatus, jqXHR) { $("#key").text(key); },
        error: function(jqXHR, textStatus, errorThrown) { $("#key").text('ERROR'); }
      });
    });

});
