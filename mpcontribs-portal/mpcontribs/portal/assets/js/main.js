import logo from 'images/logo.png';
import * as clipboard from "clipboard";
import 'select2/dist/js/select2';
import '@fortawesome/fontawesome-free/js/all';
import '@vizuaalog/bulmajs/dist/dropdown';
import introJs from 'intro.js/intro';
require('css/main.scss');

window.api = {};
var api_key = $('#api_key').val();
if (api_key !== '') {
    window.api['host'] = 'https://' + $('#api_cname').val() + '/';
    var api_key_code = window.atob(api_key);
    window.api['headers'] = {'X-API-KEY': api_key_code};
} else {
    window.api['host'] = 'http://localhost:' + $('#api_port').val() + '/';
    window.api['headers'] = {};
}
console.log(window.api);

$(document).ready(function () {
    // logo, info, api-key
    document.getElementById("logo").src = logo;
    $("#docs_url").attr("href", api_key !== '' ? 'https://mpcontribs.org' : 'http://localhost:8081');
    $('a[name="api_url"]').attr('href', window.api['host']);
    $('#api_key_btn').on('click', function() {
        clipboard.writeText(api_key_code);
        $('#api_key_text').html('Copied!');
    });

    // quick nav
    $('#jump').select2({
        ajax: {
            url: window.api['host'] + 'projects/',
            headers: window.api['headers'],
            delay: 400,
            minimumInputLength: 3,
            maximumSelectionLength: 3,
            multiple: true,
            width: 'style',
            data: function (params) {
                if (typeof params.term == 'undefined') { $("[name=cards]").removeClass('is-hidden'); }
                var query = {_fields: "name,title"};
                if (params.term) { query['description__icontains'] = params.term; }
                return query;
            },
            processResults: function (data) {
                $("[name=cards]").addClass('is-hidden');
                var results = [];
                $.each(data['data'], function(index, element) {
                    var entry = {id: index, text: element['title'], value: element['name']};
                    $('#'+element['name']).removeClass('is-hidden');
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });
    $('#jump').on('select2:select', function(ev) {
        var project = ev.params.data["value"];
        window.location.href = '/projects/'+project+'/';
    });

    // navbar burger for mobile
    $(".navbar-burger").click(function() {
        $(".navbar-burger").toggleClass("is-active");
        $(".navbar-menu").toggleClass("is-active");
    });

    $('.select2').css({width: '100%'});
    $('.select2-search').css({width: 'auto'});
    $('.select2-search__field').css({width: '100%'});

    // close all dropdowns on body click
    $('body').click(function(e) {
        var dropdowns = $(".dropdown");
        dropdowns.not(dropdowns.has(e.target)).removeClass('is-active');
    });

    $("#help").click(function() {
        // TODO use toggle name to decide which help/tour to show
        introJs().setOptions({"showStepNumbers": false, "overlayOpacity": 0.2}).start();
    });
});
