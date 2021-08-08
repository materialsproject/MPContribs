import logo from 'images/logo.png';
import '@fortawesome/fontawesome-free/js/all';
import '@vizuaalog/bulmajs/dist/dropdown';
require('css/main.scss');

var api_key = $('#api_key').val();
var api_cname = $('#api_cname').val();
var scheme = api_cname.startsWith("localhost.") ? "http" : "https"

window.api = {host: scheme + "://" + api_cname + "/"};
if (api_key !== '') { window.api['headers'] = {'X-API-KEY': api_key}; }

$(document).ready(function () {
    // logo, info, api-key
    document.getElementById("logo").src = logo;
    $('a[name="api_url"]').attr('href', window.api['host']);

    // navbar burger for mobile
    $(".navbar-burger").click(function() {
        $(".navbar-burger").toggleClass("is-active");
        $(".navbar-menu").toggleClass("is-active");
    });

    // profile dropdown
    $(".navbar-item.has-dropdown").click(function() {
        $(this).toggleClass("is-active");
    });
    $('body').click(function(e) {
        $(".navbar-item.has-dropdown").removeClass('is-active');
    });

    // close all dropdowns on body click
    $('body').click(function(e) {
        var dropdowns = $(".dropdown");
        dropdowns.not(dropdowns.has(e.target)).removeClass('is-active');
    });
});
