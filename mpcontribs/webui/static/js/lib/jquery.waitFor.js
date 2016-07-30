/* jQuery waitFor plugin
 * Version 0.1.0
 * Copyright (c) 2007-13 Bennett McElwee.
 * Licensed under the MIT licence.
 * Permissions beyond the scope of this license may be available via http://www.thunderguy.com/semicolon/
 */

/*
	IMPLEMENTATION NOTES
	There may be race conditions. The most likely could occur if check() is
	called while a previous invocation of check() is still running. This could
	cause a callback to be called more than once, or not at all. Less likely is
	for elementReady() to be called concurrently with check() (with similar
	effects) or with itself (which could cause an interval to run forever).
	None of these are likely to occur. In fact I don't think they are possible
	at all except on IE. -- Bennett McElwee, August 2007
*/
;(function($, undefined) {

/**
 * While a page is loading, call a given callback function as soon as any elements
 * matching a specific selector are loaded into the DOM, even before the full DOM
 * has been loaded. Do this by calling waitFor(), and then calling done(function() {...})
 * on the result. Call fail(function() {...}) to trigger a callback if the element
 * has not appeared by the time the full DOM is loaded.
 *
 * One argument is passed to the callback: a jQuery object containing the new elements.
 *
 * If no matching element has been found by the time the DOM is fully loaded, then
 * the fail() functions will be called.
 *
 * The function works by polling the DOM at short intervals. By default it polls
 * every 23 milliseconds, but you can change this by setting
 * $.waitFor.defaultIntervalMs before calling $.waitFor().
 * Alternatively you can pass something like {intervalMs: 100} as the third argument
 * the first time you call $.waitFor().
 * Don't bother changing this unless you really know what you're doing.
 *
 * @example
 * $.waitFor("header").done(function(elements) { elements.addClass("fancy"); });
 * @desc Add the class "fancy" to the HTML5 header element as soon as it is loaded.
 * Use $(this) to access the element as a jQuery object.
 *
 * @example
 * $.waitFor("header")
 *     .done(function(elements) { elements.addClass("fancy"); })
 *     .fail(function() { $("body").append("<p>Huh?</p>"); })
 * @desc Add the class "fancy" to the HTML5 header element as soon as it is loaded.
 * If it hasn't appeared by the time the document is ready, add a new element to the end.
 *
 * @example
 * $.waitFor.defaultIntervalMs = 100;
 * jQuery.waitFor("header").done(function(elements) {
 *     elements.addClass("fancy");
 * });
 * @desc Poll every 100ms instead of the default.
 *
 * @example
 * jQuery.waitFor("header", {intervalMs: 100}).done(function(elements) {
 *     elements.addClass("fancy");
 * });
 * @desc Another way to poll every 100ms instead of the default.
 *
 * @name   $.waitFor
 * @type   jQuery
 * @param  String   selector  string selector of the element to wait for
 * @param  object   options  options for the call
 * @return Promise
 * @cat    Plugins/Event
 * @author Bennett McElwee
 */
var interval = null;
var checklist = [];

$.waitFor = function(selector, options) {
	var options = $.extend({'intervalMs': $.waitFor.defaultIntervalMs}, options);
	var newDeferred = $.Deferred();
	checklist.push({selector: selector, deferred: newDeferred});
	if (!interval) {
		interval = setInterval(function() {
			var isLastCheck = $.isReady; // check doc ready first; thus ensure that check is made at least once _after_ doc is ready
			for (var i = checklist.length - 1; 0 <= i; --i) {
				var elements = $(checklist[i].selector);
				if (elements.length) {
					// Remove this from the checklist
					var deferred = checklist[i].deferred;
					checklist[i] = checklist[checklist.length - 1];
					checklist.pop();
					if (0 == checklist.length) {
						isLastCheck = true;
					}
					deferred.resolve(elements);
				}
			}
			if (isLastCheck) {
				clearInterval(interval);
				interval = null;
				for (var i = 0; i < checklist.length; ++i) {
					deferred.reject();
				}
				checklist = [];
			}
		}, options.intervalMs);
	}
	return newDeferred.promise();
};

// Plugin settings
$.waitFor.defaultIntervalMs = 23; // polling interval in ms

})(jQuery);
