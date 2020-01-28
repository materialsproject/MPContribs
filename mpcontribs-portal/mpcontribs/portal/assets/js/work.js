function lazyLoadImage(imageName, img) {
    import(
        /* webpackMode: "lazy-once" */
        'images/' + imageName
    ).then(function(src) {
        img.src = src.default;
        img.style.width = "100%";
    }).catch(function(err) { console.error(err); });
}

$(document).ready(function () {

    var api_key = $('#api_key').val();
    var nb_url = api_key !== '' ? 'https://jhub.mpcontribs.org' : 'http://localhost:8000';
    nb_url += '/hub/user-redirect/tree/binder/notebooks/';
    $('a[name=launch]').each(function() {
        $(this).attr('href', nb_url + $(this).attr('id') + '.ipynb');
    });

    $('a[rel=popover]').popover({
        html: true,
        trigger: 'hover',
        placement: 'bottom',
        content: function() {
            var img = document.getElementById('ingester_img');
            if (typeof(img) != 'undefined' && img != null) { return img; }
            else {
                var img = document.createElement('img');
                img.id = 'ingester_img';
                this.appendChild(img);
                lazyLoadImage('ingester.png', img);
                return img;
            }
        }
    });

    $('a[name=nb_show]').click(function(e) {
        $('a[name=nb_show]').removeClass('disabled');
        e.preventDefault();
        $('#nb_content').load('notebooks/' + $(this).html() + '.html');
        $(this).addClass('disabled');
    });
});
