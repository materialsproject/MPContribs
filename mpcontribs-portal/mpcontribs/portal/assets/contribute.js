import("./highlight.css");

function lazyLoadImage(imageName, img) {
    import(
        /* webpackMode: "lazy-once" */
        './images/' + imageName.replace('./', '')
    ).then(function(src) {
        img.src = src.default;
        img.style.width = "100%";
    }).catch(function(err) { console.error(err); });
}

$(document).ready(function () {
    var api_key = $('#api_key').val();
    var nb_url = api_key !== '' ? 'https://jhub.mpcontribs.org' : 'http://localhost:8000';
    nb_url += '/hub/user-redirect/tree/binder/notebooks/';
    document.getElementById("contribute_url").href = nb_url + 'contribute.ipynb';
    //document.getElementById("retrieve_url").href = nb_url;// + 'retrieve.ipynb';

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
});
