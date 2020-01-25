function animate() {
    $(this).children('.is-overlay').toggleClass('is-hidden');
}

$(document).ready(function () {
    import(
        /* webpackPrefetch: true */
        /* webpackChunkName: "images" */
        './images'
    );
    $('.card').mouseenter(animate);
    $('.card').mouseleave(animate);
});
