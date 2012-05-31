var template = /<!--Template:(.*)-->/

function loadIn(tag, html) {
    $(tag).empty().append(html);
    var template_name = "";
    match = html.match(template);
    if( match ) { template_name = match[1] };
//    initialize();
}

String.prototype.repeat = function( num )
{
	return new Array( num + 1 ).join( this );
}

/**
 * Renders the tabs necessary for the logged in user type
 * 
 * @param {string} type The desired tabset type
 * @return void
 */
function setTabs(type) {
	var $currentTabs = $("#tabs"),
		tabHtml;
	
	switch(type) {
		case "client":
			tabHtml = '<ul class="tabs" id="tabs"><li class="active"><a href="/client/register/creditors">Schuldendossier</a></li><li><a href="#">Mijn gegevens</a></li></ul>';
			break;
		case "organisation":
			tabHtml = '<ul class="tabs" id="tabs"><li class="active"><a href="/employee/cases/list">Dossiers</a></li></ul>';
			break;
		default:
			tabHtml = "";
	}
	
	if (tabHtml) {
		if ($currentTabs) {
			$currentTabs.remove();
		}
		$("section.content").prepend(tabHtml);
	}
}

/**
 * Enable or disable app waiting state on AJAX calls
 * 
 * @param {bool} Wether we're currently loading an AJAX resource.
 * @return void
 */
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
	$("form").live("submit",function(event) { 
		event.preventDefault();
		event.stopPropagation();
		
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
		
		$.ajax({
			url: url,
			type: method.toUpperCase(),
			data: $this.serialize(),
			headers: {"Accept":"x-text/html-fragment"},
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
				var location = jqXHR.getResponseHeader("Location");
				
				if (location) {
					if (location.match(/^https?\:\/\//)) {
						location = location.replace(/https?\:\/\/[^\/]+/,"");
					}
					
					redirected = true;
					
					// Check where we're being redirected, and set tabs accordingly
					if (location.indexOf("/client") > -1) {
						setTabs("client");
						checkLogin();
					}
					$.address.value(location);
				} else {
					$("#"+target).html(data);
					$.address.value(location);
					appLoading(false);
				}
			},
			error: function(jqXHR, textStatus, errorThrown) {
                                $('#'+target).html(textStatus + ' ' + jqXHR.responseText);
				appLoading(false);
			}
		});
	});
	
	/**
	 * Catch all links and pass them through AJAX calls
	 */
	$("a").live("click",function(event){
		var $this = $(this),
			state = {
				url : $this.attr("href"),
				target : $this.attr("target") || "content",
				title : $this.attr("data-title") || document.title,
			};
		
		event.preventDefault();
		appLoading(true);
		
		if ($this.attr("data-actions") && $this.attr("data-actions").indexOf("close-popup") > -1) {
			$("#popup").removeClass("active");
		}
		
		if (state.target === "_popup") {
			$("#popup .content").load(state.url,function(){
				var $popup = $("#popup"),
					$popupContent = $popup.find(".content");
				
				$popup.find("a").attr("data-actions","close-popup")
				$popup.addClass("active");
				$popupContent.css("margin-left","-" + ($popupContent.width() / 2) + "px");
				appLoading(false);
			});
		} else {
			$.address.value(state.url);
		}
	});
        $(":checkbox.check").live("click",function(event) {
               var checked = $(this).is(':checked');
               var creditor = $(this).val()
               var url = $(this).closest("form").attr("action");
               $.post(url, { checked: checked, creditor: creditor },
                   function( html ) {
                       document.body.style.cursor = "default";
                       loadIn('#content', html);
                       document.body.style.cursor = "default";
               });

        });	
	/**
	 * jQuery.address change handler
	 * 
	 * @param {object} The change event
	 * @return {void}
	 */
    $.address.change(function(event) {
        if(event.path == '/') return;
        document.body.style.cursor = "wait";
        $.ajax({
            type: "GET",
            url: event.value,
            //data: event.parameters,
            success: function(html, textStatus, jqXHR) {
                loadIn('#content', html);
                document.body.style.cursor = "default";
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $('#content').empty().append(textStatus + ' ' + jqXHR.responseText);
                document.body.style.cursor = "default";
            }
        });
    });
    checkLogin();
});

function checkLogin() {
	$.ajax({
		url: "/login",
		type: "GET",
		headers: {"Accept":"x-text/html-fragment"},
		success: function(data, textStatus, jqXHR) {
			if (data.match("U bent ingelogd")) {
				$("#login").replaceWith('<p id="login">' + data + "</p>");
				setTabs("client");
			}
		},
		error: function(jqXHR, textStatus, errorThrown) {
			appLoading(false);
		}
	});
}

