function lazyLoadImage(imageName, img) {
    import(
        /* webpackMode: "lazy-once" */
        '../images/' + imageName.replace('./', '')
    ).then(function(src) {
        img.src = src.default;
        img.style.width = "100%";
    }).catch(function(err) { console.log(err); });
}

function generateImage(container, imageName) {
    var img = document.createElement('img');
    container.appendChild(img);
    lazyLoadImage(imageName, img);
}

function getImages() {
    return require.context('../images/', false, /\.(jpe?g)$/).keys();
}

var imageNames = getImages();
$.each(imageNames, function(idx, name) {
    var selector = '#thumbnail_' + name.replace('./', '').replace('.jpg', '_img');
    var container = document.querySelector(selector);
    if (container) { generateImage(container, name); }
})
