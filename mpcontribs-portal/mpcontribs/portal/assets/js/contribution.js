import hljs from "highlight-core";
import python from "highlight-languages";

$(document).ready(function () {

    hljs.registerLanguage('python', python);
    hljs.highlightAll();
    $('div.input, pre, .hljs').addClass('has-background-dark');
    $('div.input').css("height", "100%");
    $('pre').addClass('is-paddingless');
    $('h2').addClass('title');

    $('.anchor-link').each(function(index, anchor) {
        var href = $(anchor).attr('href');
        var text = href.substring(1).split('-')[0];
        var a = $('<a/>', {'href': href, 'text': text, 'class': 'button is-white'});
        var item = $('<div/>', {'class': 'level-item', 'html': a});
        $('#anchors').append(item);
        $('#item_' + text).removeClass('is-hidden');
    });
});
