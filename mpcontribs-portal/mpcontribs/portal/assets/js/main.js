import img from 'images/logo.png';
import * as clipboard from "clipboard";
import 'select2/dist/js/select2';
import 'jquery-simulate/jquery.simulate';
import * as bulmaTagsinput from 'bulma-extensions/bulma-tagsinput/dist/js/bulma-tagsinput';
import bulmaCollapsible from '@creativebulma/bulma-collapsible/dist/js/bulma-collapsible.min';
require('css/main.scss');

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

window.api = {};
var api_key = $('#api_key').val();
if (api_key !== '') {
    console.log(process.env.API_CNAME);
    window.api['host'] = 'https://' + process.env.API_CNAME + '/';
    var api_key_code = window.atob(api_key);
    window.api['headers'] = {'X-API-KEY': api_key_code};
} else {
    window.api['host'] = 'http://localhost:5000/';
    window.api['headers'] = {};
}

$(document).ready(function () {
    // logo, info, api-key
    document.getElementById("logo").src = img;
    document.getElementById("docs_url").href = api_key !== '' ? 'https://mpcontribs.org' : 'http://localhost:8081';
    $('a[name="api_url"]').attr('href', window.api['host']);
    $('#api_key_btn').on('click', function() {
        clipboard.writeText(api_key_code);
        $('#api_key_text').html('Copied!');
    });

    // quick nav
    $('#jump').select2({
        allowClear: true,
        ajax: {
            url: window.api['host'] + 'projects/',
            headers: window.api['headers'],
            delay: 400,
            minimumInputLength: 3,
            maximumSelectionLength: 3,
            multiple: true,
            width: 'style',
            data: function (params) {
                if (typeof params.term == 'undefined') { $("div[name=cards]").removeClass('is-hidden'); }
                var query = {_fields: "project,title"};
                if (params.term) { query['description__icontains'] = params.term; }
                return query;
            },
            processResults: function (data) {
                $("div[name=cards]").addClass('is-hidden');
                var results = [];
                $.each(data['data'], function(index, element) {
                    var entry = {id: index, text: element['title'], value: element['project']};
                    $('#'+element['project']).removeClass('is-hidden');
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });
    $('#jump').on('select2:select', function(ev) {
        var project = ev.params.data["value"];
        window.location.href = '/'+project+'/';
    });

    // navbar burger for mobile
    $(".navbar-burger").click(function() {
        $(".navbar-burger").toggleClass("is-active");
        $(".navbar-menu").toggleClass("is-active");
    });

    // toggle nav
    $.each(['browse', 'search', 'apply', 'work'], function(idx, toggle) {
        var selector = '#' + toggle + '-toggle';
        $(selector).on('click', function() {
            $('#api_key_text').html('API Key');
            $('.navbar-burger.is-active').simulate('click');
            var li = $(this).parent();
            li.siblings().removeClass('is-active');
            $('section').addClass('is-hidden');
            $('#' + toggle).removeClass('is-hidden');
            $(this).parent().addClass('is-active');
            import(
                /* webpackPrefetch: true */
                /* webpackMode: "lazy-once" */
                './' + toggle + '.js'
            ).then(function() {
                if (!$('.tagsinput').length) { bulmaTagsinput.attach('[type="tags"]'); }
                //bulmaCollapsible.attach('.is-collapsible');
                if ($('#'+toggle+'-help').length) {
                    var help = $('#'+toggle+'-help').html();
                    $('#main-help-text').html(help);
                    $('#main-help').removeClass('is-hidden');
                } else {
                    $('#main-help-text').html('');
                    $('#main-help').addClass('is-hidden');
                }
                $("#main-help-button").click(function () { $(".dropdown").toggleClass("is-active"); });
                $("#main-help-button").blur(function () { $(".dropdown").removeClass("is-active"); });
                console.log(toggle + ' imported');
            }).catch(function(err) { console.error(err); });
        });
    });

    //if ($("#landingpage").length) {
    //    import(/* webpackChunkName: "landingpage" */ `./landingpage.js`).catch(function(err) { console.error(err); });
    //}

    //if ($("#contribution").length) {
    //    import(/* webpackChunkName: "contribution" */ `./contribution.js`).catch(function(err) { console.error(err); });
    //}

    $('.select2').css({width: '100%'});
    $('.select2-search').css({width: 'auto'});
    $('.select2-search__field').css({width: '100%'});

    // click the toggle based on location
    if (window.location.hash) {
        var selector = '#' + window.location.hash.split('-')[0].slice(1) + '-toggle';
        $(selector).simulate('click');
    } else {
        $('#browse-toggle').click();
    }
});
