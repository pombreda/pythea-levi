String.prototype.repeat = function( num )
{
    return new Array( num + 1 ).join( this );
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
        $("body").css("cursor","wait");
    } else {
        $("body").css("cursor","default");
    }
}

$(document).ready(function(){

    // Make sure that clicking outside the popup content will close the popup
    $(".popup .overlay").click(function(){
        $("#popup a.popup-close").trigger("click");
    });

    // Make sure submit button values are included in AJAX calls
    $("input[type=submit]").live("click",function(e){
        var $this = $(this),
            setValue;
        if ($this.attr("name") && $this.attr("value")) {
            setValue = [$this.attr("name"),$this.attr("value")];
        } else if ($this.attr("data-set-value") && $this.attr("data-set-value").indexOf("=") > 0) {
            setValue = $this.attr("data-set-value").split("=");
        }

        if (setValue) {
            console.log("Submit value set: ",setValue);
            $this.after('<input type="hidden" name="'+setValue[0]+'" value="'+setValue[1]+'">');
        }
    });

    // Catch all form execution and pass it through AJAX calls
    $("#content form").live("submit",function(event) {
        event.preventDefault();
        event.stopPropagation();

        appLoading(true);
        var $this = $(this),
            url = $this.attr("action"),
            method = $this.attr("method") ? $this.attr("method").toLowerCase() : "get"
            target = $this.attr("target") ? $this.attr("target").toLowerCase() : "content",
            context = this,
            redirected = false
            ;

        $.ajax({
            url: url,
            type: method.toUpperCase(),
            // Used to be:
            // data: this.serialize(),
            data: new FormData($this[0]),
            headers: {"Accept":"x-text/html-fragment", "Accept-Language":"nl"},
            context: context,
            // Required to handle form data
            cache: false,
            contentType: false,
            processData: false,

            success: function(data, textStatus, jqXHR) {
                var location = jqXHR.getResponseHeader("Location");

                if (location) {
                    if (location.match(/^https?\:\/\//)) {
                        location = location.replace(/https?\:\/\/[^\/]+/,"");
                    }

                    if (data != "") {
                        setAppStatus(data);
                    }

                    redirected = true;
                    if(target == '_popup') {
                        loadPopup(location);
                    } else {
                        if( location == $.address.value() ) {
                            $.address.update();
                        } else {
                            $.address.value(location);
                        }
                        prepareForms();
                    }
                } else if ($("#"+target)) {
                    $("#"+target).html(data);
                    setAppStatus();
                    setAppButtons();
                    //$.address.value(location);
                    appLoading(false);
                }
                checkLogin();
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $('#'+target).html(textStatus + ' ' + jqXHR.responseText);
                appLoading(false);
            }
        });
    });

    /**
     * HTH: FIXME: this does not appear to be used anymore.
     * Enable the popup close button
    $("#popup-close").live("click",function(e){
        e.preventDefault();
        e.stopPropagation();
        $("#popup").removeClass("active");
        $(".content","#popup").empty();
        return false;
    });
    */
    /**
     * Catch all links and pass them through AJAX calls
     */
    $("#content a:not([target=_popup]), header a:not([target=_top]), .tabs a").live("click",function(event){
        var $this = $(this),
            state = {
                url : $this.attr("href"),
                target : $this.attr("target") || "content",
                title : $this.attr("data-title") || document.title,
            };

        event.preventDefault();
        if (state.url === "#") {
            return false;
        }
        if (state.url === $.address.value()) {
            return false;
        }
        if (state.url === "/client/register" && $("a[href='/logout']")) {
            // User wants to register. Clear running session if applicable.
            document.location = "/logout?redirect="+encodeURIComponent("/#" + state.url);
            return false;
        }
        appLoading(true);

        if (state.target !== "content" && $("#"+state.target)) {
            $("#"+state.target).load(state.url,function(){
                appLoading(false);
                setAppStatus();
                setAppButtons();
            });
        } else {
            $.address.value(state.url);
        }
    });

    $("#popup a[target=_close]").live("click",function(event) {
        event.preventDefault();
        $('#popup .content').empty();
        $("#popup").removeClass("active");
        var anchor = $(this);
        var url = anchor.attr("href");
        $.get(url, {},
            function( html ) {
                setAppStatus(html);
        });
    });
    $("#popup a[target=_blank]").live("click",function(event) {
        $('#popup .content').empty();
        $("#popup").removeClass("active");
    });
    /*
    /*
     * Load a link into the popup screen
     */
    $("a[target=_popup]").live("click",function(event) {
        event.preventDefault();
        var anchor = $(this);
        var url = anchor.attr("href");
        var hidden = anchor.children("input[type=hidden]");
        appLoading(true);
        $("#popup .popup-content").load(url,function(){
            $('#popup').addClass("active");
            appLoading(false);

            $popupContent = $("#popup .popup-wrapper");
            $popupContent.css("margin-left","-" + Math.min($popupContent.width()/2, 470) + "px");
            $popupCloser = $("#popup .close");
            $popupCloser.css("margin-right","-" + ($popupContent.width() / 2) + "px");
            prepareForms();

            /*
             * And close it again when something is selected.
             */
            $("#popup a.popup-select").click(function(event) {
                event.preventDefault();
                var target = $(event.currentTarget);
                var text = target.html().trim();
                var selection = target.attr("href").split('=')[1];
                anchor.html(text+"<input type='hidden' name='selected' value='"+selection+"'>");
                $('input[name=selected]').val(selection);
                $("#popup").removeClass("active");
            });
            $("#popup a.popup-close").click(function(event) {
                event.preventDefault();
                $('#popup .content').empty();
                $("#popup").removeClass("active");
            });
        });
    });

    /*
     * When a creditor is selected, add it to the database
     */
    $(":checkbox.check").live("click",function(event) {
        var checked = $(this).is(':checked');
        var creditor = $(this).val();
        var category = $('.selector-container li.active a')[0].innerText;
        if (creditor === "new") {
           $.address.value("/client/creditors/category/"+category+"/new");
           return;
        };
        var url = $(this).closest("form").attr("action");
        document.body.style.cursor = "wait";
        $.post(url, { checked: checked, creditor: creditor },
            function( html ) {
                $('#selected ul').html(html);
                setAppStatus();
                setAppButtons();
                document.body.style.cursor = "default";
                prepareForms();
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
        $("#tabs a").each( function( index, object ) {
            var obj = $(object);

            if( event.path.indexOf(object.pathname) != -1 ) {
                $(object).parent().addClass("active");
            } else {
                $(object).parent().removeClass("active");
            }
        });
        $('#popup .popup-content').empty();
        $("#popup").removeClass("active");

        document.body.style.cursor = "wait";
        $.ajax({
            type: "GET",
            url: event.value,
            data: event.parameters,
            headers: {"Accept":"x-text/html-fragment", "Accept-Language":"nl"},
            success: function(html, textStatus, jqXHR) {
                var location = jqXHR.getResponseHeader("Location");
                if (location) {
                    if (location.match(/^https?\:\/\//)) {
                        location = location.replace(/https?\:\/\/[^\/]+/,"");
                    }
                    $.address.value(location);
                    return;
                }
                $('#content').html(html);
                setAppStatus();
                setAppButtons();

                document.body.style.cursor = "default";
                prepareForms();
                checkLogin();
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $('#content').empty().append(textStatus + ' ' + jqXHR.responseText);
                document.body.style.cursor = "default";
            }
        });
    });
    /**
     * Check the registration form
     * FIXME: Only add the suggested username if the form is displayed for the first time.
     */
    // var obj = $('#id_firstname');
    // if ( $('#id_username').val() ) {
    // } else {
    //    $("input[name=first_name],input[name=last_name]").live("blur",function(event) {
    //       username = $("#id_first_name").val().toLowerCase().replace(/\s+/,"_")+
    //                  '.'+
    //                  $("#id_last_name").val().toLowerCase().replace(/\s+/,"_");
    //       $('#id_username').val(username);
    //    });
    // }
    $("a","#tabs").live("click",function(e){
        $("li","#tabs").removeClass("active");
        $(this).parent().addClass("active");
    });


    /* If the user selects a radio button, we immediately submit  */
    /* FIXME: DISCUSS: add an onclick=this.form.submit(); Easier than this */
    $(".contact-list input[type=radio]").live("click", function(e) {
        var url = $(this).closest("form").attr("action");
        var selected = $(this).val();
        document.body.style.cursor = "wait";
        $.post(url, { selected: selected },
            function( html ) {
                $.address.value("/client/creditors");
                document.body.style.cursor = "default";
            });

    });

    // Enable datepicker fields
    $.datepicker.setDefaults({dateFormat: "yy-mm-dd"});
    prepareForms();

});

// Preprare logic for all forms present
function prepareForms() {
    /*
    Enable datepicker for any date.input
    Since jQuery UI prevents setting multiple pickers on the same element,
    this can safely be run multiple times
     */
    $("input.date").datepicker();

    // Prepare username field for registration form
    handleUsername();
}

/*
On the registration and user info forms, prevent the username from being changed before first submit, or after registration
*/
function handleUsername() {
    // Find elements
    var $form = $("form[action='/client/register'],form[action='/client/info']"),
        $username = $form.find("input[name=username]"),
        $tbody = $username.parents("tbody[class]");

    // Only operate if all necessary elements are pesent
    if ($form.length > 0 && $username.length > 0 && $tbody.length > 0) {
        if (!$username.attr("readonly") && ($tbody.hasClass("unposted") || $tbody.hasClass("free") || $tbody.hasClass("instance"))) {

            // Form is either new or an existing instance. The username cannot be changed
            $username.attr("readonly","readonly");

            // Since username is inmutable here, we can assume that an empty field equals a new username
            // Set up a listener to auto-populate with first_name.last_name
            if ($username.val() == "" && $username.attr("readonly")) {
                $form.find("input[name=first_name],input[name=last_name]").live("change",function(event) {
                    var username = $("#id_first_name").val().toLowerCase().replace(/\s+/,"_");
                        username += '.';
                        username += $("#id_last_name").val().toLowerCase().replace(/\s+/,"_");
                    $username.val(username);
                });
            }
        }
    }
}


/*
 *  HTH: This does not appear to be used.
 */
function checkLogin() {
    var $login = $(".login"),
        $userIdElement = $("#user-id",$login),
        userId = $("#session-user").html();

    if (!$login.hasClass("session-active") && !userId.match(/^\s*$/)) {
        $userIdElement.html(userId);
        $login.addClass("session-active");
    }
}

/*
 *  HTH: This does not appear to be used.
 *  */
function loadPopup(url) {
    $('#popup').addClass("active");
    appLoading(true);
    $("#popup .popup-content").load(url,function(){
        var $popup = $("#popup"),
            $popupContent = $(".content",$popup),
            $popupCloser = $(".close",$popup);

        $popup.addClass("active");
        $popupCloser.css("margin-right","-" + ($popupContent.width() / 2) + "px");
        appLoading(false);
        $("#popup a.popup-close").click(function(event) {
            event.preventDefault();
            $('#popup .content').empty();
            $("#popup").removeClass("active");
        });
    });
}

function setAppStatus(status) {
    var effect = false;

    if (!status && $('#message')) {
        status = $('#message').html();
    }
    if (!status) {
        status = "&nbsp;";
    }
    if ($("#appstatus").length > 0) {
        if (typeof status === "string") {
            if (status === "") {
                status = "&nbsp;";
            } else if (!status.match(/^\s+$/) && status != "&nbsp;") {
                effect = true;
            }
        }
           $("#appstatus").html(status);
        if (effect) {
            setTimeout(function(){$("#appstatus").addClass("update");},100);
            setTimeout(function(){$("#appstatus").removeClass("update");},1000);
        }
    } else {
        $("#content").parent().prepend('<p id="appstatus" class="appstatus">'+status+'</p>');
    }
    $("#tabs").html($("#session-tabs").html());
    // alert($("#session-tabs").html());
}

function setAppButtons() {
    var $appButtons = $("#appbuttons"),
        $appControls = $(".app-control");

    $appButtons.empty();
    if ($appControls.length > 0) {
        $appControls.each(function(i,e){
            var $origButton = $(this),
                $appbuttons = $("#appbuttons"),
                id = $origButton.attr("id"),
                name = $origButton.attr("name"),
                value = $origButton.attr("value"),
                ctrlId = "ctrl-"+(id || name),
                newButton = "<button id=\""+ctrlId+"\">"+value+"</button>";

            $appbuttons.append(newButton);
            $("button:last-child",$appbuttons).click(function(){
                $origButton.trigger("click");
            });

            $origButton.addClass("app-control-set");

        });
    }
}
