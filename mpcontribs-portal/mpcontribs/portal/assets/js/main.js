import img from 'images/logo.png';
import * as clipboard from "clipboard";
import 'select2/dist/js/select2';
import 'jquery-simulate/jquery.simulate';
import '@fortawesome/fontawesome-free/js/all';
import '@vizuaalog/bulmajs/dist/dropdown';
import * as bulmaTagsinput from 'bulma-extensions/bulma-tagsinput/dist/js/bulma-tagsinput';
//import bulmaCollapsible from '@creativebulma/bulma-collapsible/dist/js/bulma-collapsible.min';
require('css/main.scss');

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

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
    document.getElementById("logo").src = img;
    document.getElementById("docs_url").href = api_key !== '' ? 'https://mpcontribs.org' : 'http://localhost:8081';
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
                var query = {_fields: "project,title"};
                if (params.term) { query['description__icontains'] = params.term; }
                return query;
            },
            processResults: function (data) {
                $("[name=cards]").addClass('is-hidden');
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
    var toggles = ['browse', 'search', 'apply', 'work'];
    $.each(toggles, function(idx, toggle) {
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
                console.log(toggle + ' imported');
            }).catch(function(err) { console.error(err); });
        });
    });

    if ($("#landingpage").length) {
        import(
            /* webpackPrefetch: true */
            /* webpackMode: "lazy" */
            /* webpackChunkName: "landingpage" */
            `./landingpage.js`
        ).then(function() {
            console.log('landingpage imported.')
        }).catch(function(err) { console.error(err); });
    }

    if ($("#contribution").length) {
        import(
            /* webpackPrefetch: true */
            /* webpackMode: "lazy" */
            /* webpackChunkName: "contribution" */
            `./contribution.js`
        ).then(function() {
            console.log('contribution imported.')
        }).catch(function(err) { console.error(err); });
    }

    $('.select2').css({width: '100%'});
    $('.select2-search').css({width: 'auto'});
    $('.select2-search__field').css({width: '100%'});

    // click the toggle based on location (for manual reloads or links including hash)
    if (window.location.pathname === '/') {
        if (window.location.hash) {
            var toggle = window.location.hash.slice(1);
            var selector = '#' + toggle + '-toggle';
            $(selector).simulate('click');
        } else  {
            $('#browse-toggle').simulate('click');
        }
        $("html, body").animate({ scrollTop: 0 }, 1);
    } else {
        $('.navbar-start .navbar-item .tabs ul li').removeClass('is-active');
    }

    // close all dropdowns on body click
    $('body').click(function(e) {
        var dropdowns = $(".dropdown");
        dropdowns.not(dropdowns.has(e.target)).removeClass('is-active');
    });
});
