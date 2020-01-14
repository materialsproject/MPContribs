import 'bootstrap';
import 'select2';
import {Spinner} from 'spin.js';
require("./product_card.css");

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

var fields = ['formula', 'project', 'identifier'];
var spinner = new Spinner({scale: 0.5, color: 'white'});

function get_single_selection(field) {
    var select = $('#'+field+'s_list').select2("data");
    return $.map(select, function(sel) { return sel['text']; }).join(',');
}

function get_selection(field) {
    return $.map(fields, function(f) {
        return (f !== field) ? get_single_selection(f) : '';
    });
}

function get_query(selection) {
    var query = {_limit: 7};
    $.each(selection, function(idx, sel) {
        if (sel !== '') { query[fields[idx] + '__in'] = sel; }
    });
    return query;
}

function getData(field) {
    return function (params) {
        var query = get_query(get_selection(field));
        if (params.term) { query[field + '__contains'] = params.term; }
        query['_fields'] = 'id,' + field;
        return query;
    }
}

function processResults(field) {
    return function (data) {
        var texts = new Set();
        var results = $.map(data['data'], function(d) {
            if (!texts.has(d[field])) {
                texts.add(d[field]);
                var id = d.hasOwnProperty('id') ? d['id'] : d[field];
                return {id: id, text: d[field]};
            }
        });
        return {results: results};
    }
}

function get_ajax(field) {
    var endpoint = (field == 'project') ? 'projects/' : 'contributions/';
    var api_url = window.api['host'] + endpoint;
    return {
        url: api_url, headers: window.api['headers'],
        delay: 400, minimumInputLength: 2, maximumSelectionLength: 3,
        multiple: true, width: 'style',
        data: getData(field), processResults: processResults(field)
    }
}

function render_card(cid) {
    var target = document.getElementById('spinner');
    spinner.spin(target);
    var url = window.api['host'] + 'cards/' + cid + '/';
    $.get({url: url, headers: window.api['headers']}).done(function(response) {
        $('#card').html(response['html']);
        spinner.stop();
    });
}

function search(event) {
    event.preventDefault(); // To prevent following the link (optional)
    var selection = $.map(fields, function(f) { return get_single_selection(f); });
    var filtered_selection = selection.filter(function (el) { return el !== ''; });
    if (filtered_selection.length === 0) { alert('Please make a selection'); }
    else {
        var query = get_query(selection)
        var api_url = window.api['host'] + 'contributions/';
        var btnId = $(this).attr('id');
        if (btnId.endsWith('Show')) {
            $.get({
                url: api_url, data: query, headers: window.api['headers']
            }).done(function(response) {
                $('#count').html(response['total_count'] + ' result(s)');
                $('#results').empty();
                $.each(response['data'], function(i, d) {
                    var btn = $('<a/>', {
                        'class': "btn btn-link", 'role': 'button', 'style': "padding: 0", 'id': d['id'], 'text': d['id']
                    });
                    var info = $('<span/>', {text: ' (' + d['formula'] + ', ' + d['project'] + ', ' + d['identifier'] + ')'});
                    var li = $('<li/>');
                    btn.on('click', search);
                    li.append(btn);
                    li.append(info);
                    $('#results').append(li);
                });
            });
        } else {
            $("#card").empty();
            render_card(btnId);
        }
    }
}


$(document).ready(function () {
    import(
        /* webpackPrefetch: true */
        /* webpackChunkName: "images" */
        './images'
    );
    $('.btn-link').tooltip();
    $('div[name=card-contrib]').each(function() {
        render_json({divid: $(this).attr('id'), data: $(this).data('contrib')});
    });

    // selects
    $.each(fields, function(idx, field) {
        $('#'+field+'s_list').select2({placeholder: 'Select '+field+'(s) ...', ajax: get_ajax(field)});
    });
    $('.select2-search').css({width: 'auto'});
    $('.select2-search__field').css({width: '100%'});

    // bind button events and show example card
    $('#btnShow').on('click', search);
    render_card('5a862202d4f1443a18fab254');

    $('#explorer_form').show();

    // Lift card and show stats on Mouseover
	$('#product-card').hover(function(){
			$(this).addClass('animate');
			$('div.carouselNext, div.carouselPrev').addClass('visible');
		 }, function(){
			$(this).removeClass('animate');
			$('div.carouselNext, div.carouselPrev').removeClass('visible');
	});

	// Flip card to the back side
	$('#view_details').click(function(){
		$('div.carouselNext, div.carouselPrev').removeClass('visible');
		$('#product-card').addClass('flip-10');
		setTimeout(function(){
			$('#product-card').removeClass('flip-10').addClass('flip90').find('div.shadow').show().fadeTo( 80 , 1, function(){
				$('#product-front, #product-front div.shadow').hide();
			});
		}, 50);

		setTimeout(function(){
			$('#product-card').removeClass('flip90').addClass('flip190');
			$('#product-back').show().find('div.shadow').show().fadeTo( 90 , 0);
			setTimeout(function(){
				$('#product-card').removeClass('flip190').addClass('flip180').find('div.shadow').hide();
				setTimeout(function(){
					$('#product-card').css('transition', '100ms ease-out');
					$('#cx, #cy').addClass('s1');
					setTimeout(function(){$('#cx, #cy').addClass('s2');}, 100);
					setTimeout(function(){$('#cx, #cy').addClass('s3');}, 200);
					$('div.carouselNext, div.carouselPrev').addClass('visible');
				}, 100);
			}, 100);
		}, 150);
	});

	// Flip card back to the front side
	$('#flip-back').click(function(){

		$('#product-card').removeClass('flip180').addClass('flip190');
		setTimeout(function(){
			$('#product-card').removeClass('flip190').addClass('flip90');

			$('#product-back div.shadow').css('opacity', 0).fadeTo( 100 , 1, function(){
				$('#product-back, #product-back div.shadow').hide();
				$('#product-front, #product-front div.shadow').show();
			});
		}, 50);

		setTimeout(function(){
			$('#product-card').removeClass('flip90').addClass('flip-10');
			$('#product-front div.shadow').show().fadeTo( 100 , 0);
			setTimeout(function(){
				$('#product-front div.shadow').hide();
				$('#product-card').removeClass('flip-10').css('transition', '100ms ease-out');
				$('#cx, #cy').removeClass('s1 s2 s3');
			}, 100);
		}, 150);

	});


	/* ----  Image Gallery Carousel   ---- */
	var carousel = $('#carousel ul');
	var carouselSlideWidth = 335;
	var carouselWidth = 0;
	var isAnimating = false;

	// building the width of the casousel
	$('#carousel li').each(function(){
		carouselWidth += carouselSlideWidth;
	});
	$(carousel).css('width', carouselWidth);

	// Load Next Image
	$('div.carouselNext').on('click', function(){
		var currentLeft = Math.abs(parseInt($(carousel).css("left")));
		var newLeft = currentLeft + carouselSlideWidth;
		if(newLeft == carouselWidth || isAnimating === true){return;}
		$('#carousel ul').css({'left': "-" + newLeft + "px", "transition": "300ms ease-out" });
		isAnimating = true;
		setTimeout(function(){isAnimating = false;}, 300);
	});

	// Load Previous Image
	$('div.carouselPrev').on('click', function(){
		var currentLeft = Math.abs(parseInt($(carousel).css("left")));
		var newLeft = currentLeft - carouselSlideWidth;
		if(newLeft < 0  || isAnimating === true){return;}
		$('#carousel ul').css({'left': "-" + newLeft + "px", "transition": "300ms ease-out" });
	    isAnimating = true;
		setTimeout(function(){isAnimating = false;}, 300);
	});
});
