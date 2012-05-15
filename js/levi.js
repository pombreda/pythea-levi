String.prototype.repeat = function( num )
{
	return new Array( num + 1 ).join( this );
}

// Enable or disable app waiting state on AJAX calls
function appLoading(loading) {
// @TODO: This stuff should be handled with classes
	if (loading) {
		$("body").css("cursor","waiting");
	} else {
		$("body").css("cursor","default");
	}
}

$(document).ready(function(){

// Set up automated validation for login form
$("#login").validate();

// Catch all form execution and pass it through AJAX calls
$("form").on("submit",function(event) { 
	event.preventDefault();
	
	var $this = $(this),
		url = $this.attr("action"),
		method = $this.attr("method") ? $this.attr("method").toLowerCase() : "get"
		target = $this.attr("target") ? $this.attr("target").toLowerCase() : "content",
		context = this,
		redirected = false
		;
	
	// If validation marked any errors, stop processing.
	if ($this.find("input.error").length > 0) {
		return;
	}
	
	//data = $(this).serialize();
	
	if (method === "get") {
		$.address.value(url + '?' + data);
	} else {
		$.address.value(url);
	}
	
	$.ajax({
		url: url,
		type: method.toUpperCase(),
		data: $this.serialize(),
		headers: {"Accepts":"x-text/html-fragment"},
		context: context,
		beforeSend: function(jqXHR, settings) {
			appLoading(true);
		},
		complete: function(jqXHR, textStatus) {
			if (!redirected) {
				appLoading(false);
			}
		},
		success: function(data, textStatus, jqXHR) {
			
			console.log("Successful AJAX call!");
			console.log("Location header: ",jqXHR.getResponseHeader("Location"));
			console.log("data: ",data);
			console.log("textStatus: ",textStatus);
			console.log("jqXHR: ",jqXHR);
			console.log("-".repeat(80));
			
			$("#"+target).html(data);
			appLoading(false);
		},
		error: function(jqXHR, textStatus, errorThrown) {
			appLoading(false);
			
			if (typeof window.console === "object" && typeof console.error === "function") {
				console.error("AJAX call error!");
				console.log("Location header: ",jqXHR.getResponseHeader("Location"));
				console.log("jqXHR: ", jqXHR);
				console.log("textStatus: ", textStatus);
				console.log("errorThrown: ", errorThrown);
				console.log("-".repeat(80));
			}
		}
	});
});

// Catch all links and pass them through AJAX calls
$("a").on("click",function(event){
	event.preventDefault();
	
	var $this = $(this),
		url = $this.attr("href"),
		target = $this.attr("target") || "content",
		context = this,
		redirected = false
		;
	
	$.ajax({
		url: url,
		context: context,
		beforeSend: function(jqXHR, settings) {
			appLoading(true);
		},
		complete: function(jqXHR, textStatus) {
			if (!redirected) {
				appLoading(false);
			}
		},
		success: function(data, textStatus, jqXHR) {
			console.log("Successful AJAX call!",data, textStatus, jqXHR);
			$("#"+target).html(data);
			appLoading(false);
		},
		error: function(jqXHR, textStatus, errorThrown) {
			appLoading(false);
			
			if (typeof window.console === "object" && typeof console.error === "function") {
				console.error("AJAX call error!", jqXHR, textStatus, errorThrown);
			}
		}
	});
});

});