const body = document.body;

const deleteForm =
    document.getElementById("deleteForm");

const startDeleteButton =
    document.getElementById("startDeleteButton");

const cancelDeleteButton =
    document.getElementById("cancelDeleteButton");

const prepareDeleteButton =
    document.getElementById("prepareDeleteButton");

const noticeModal =
    document.getElementById("noticeModal");

const noticeTitle =
    document.getElementById("noticeTitle");

const noticeMessage =
    document.getElementById("noticeMessage");

const closeNoticeButton =
    document.getElementById("closeNoticeButton");

const confirmModal =
    document.getElementById("confirmModal");

const confirmDeleteMessage =
    document.getElementById("confirmDeleteMessage");

const cancelConfirmButton =
    document.getElementById("cancelConfirmButton");

const confirmDeleteButton =
    document.getElementById("confirmDeleteButton");


// =========================================================
// DELETE CHECKBOXES
// =========================================================

const dateSelectors = Array.from(
    document.querySelectorAll(
        ".date-delete-selector"
    )
);

const dateCheckboxes = Array.from(
    document.querySelectorAll(
        ".date-checkbox"
    )
);

const parentCheckboxes = Array.from(
    document.querySelectorAll(
        ".parent-checkbox"
    )
);


// =========================================================
// SELECTED PARENT EMAILS
// =========================================================

function selectedCheckboxes() {
    return Array.from(
        document.querySelectorAll(
            ".parent-checkbox:checked"
        )
    );
}


// =========================================================
// GET ALL PARENT CHECKBOXES FOR ONE DATE
// =========================================================

function getParentCheckboxesForDate(
    dateValue
) {
    return parentCheckboxes.filter(
        function (checkbox) {
            return (
                checkbox.dataset.date ===
                dateValue
            );
        }
    );
}


// =========================================================
// UPDATE DATE CHECKBOX STATE
// =========================================================

function updateDateCheckbox(
    dateCheckbox
) {
    const dateValue =
        dateCheckbox.dataset.date;

    const children =
        getParentCheckboxesForDate(
            dateValue
        );

    if (children.length === 0) {
        dateCheckbox.checked = false;
        dateCheckbox.indeterminate = false;
        return;
    }

    const checkedCount =
        children.filter(
            function (checkbox) {
                return checkbox.checked;
            }
        ).length;

    dateCheckbox.checked =
        checkedCount === children.length;

    dateCheckbox.indeterminate =
        checkedCount > 0 &&
        checkedCount < children.length;
}


// =========================================================
// UPDATE ALL DATE CHECKBOXES
// =========================================================

function updateAllDateCheckboxes() {
    dateCheckboxes.forEach(
        function (dateCheckbox) {
            updateDateCheckbox(
                dateCheckbox
            );
        }
    );
}


// =========================================================
// SHOW DATE CHECKBOXES
// =========================================================

function showDateSelectors() {
    dateSelectors.forEach(
        function (selector) {
            selector.classList.remove(
                "is-hidden"
            );
        }
    );

    updateAllDateCheckboxes();
}


// =========================================================
// HIDE DATE CHECKBOXES
// =========================================================

function hideDateSelectors() {
    dateSelectors.forEach(
        function (selector) {
            selector.classList.add(
                "is-hidden"
            );
        }
    );

    dateCheckboxes.forEach(
        function (checkbox) {
            checkbox.checked = false;
            checkbox.indeterminate = false;
        }
    );
}


// =========================================================
// CLEAR ALL SELECTIONS
// =========================================================

function clearSelections() {
    parentCheckboxes.forEach(
        function (checkbox) {
            checkbox.checked = false;
        }
    );

    dateCheckboxes.forEach(
        function (checkbox) {
            checkbox.checked = false;
            checkbox.indeterminate = false;
        }
    );
}


// =========================================================
// DATE CHECKBOX
//
// IMPORTANT:
// Save targetChecked before modifying the children.
//
// Otherwise, after the first child is checked,
// the date checkbox can become indeterminate/unchecked,
// causing only the first account to be selected.
// =========================================================

dateCheckboxes.forEach(
    function (dateCheckbox) {

        dateCheckbox.addEventListener(
            "change",
            function () {

                const targetChecked =
                    dateCheckbox.checked;

                const children =
                    getParentCheckboxesForDate(
                        dateCheckbox.dataset.date
                    );

                children.forEach(
                    function (checkbox) {
                        checkbox.checked =
                            targetChecked;
                    }
                );

                dateCheckbox.indeterminate =
                    false;

                updateDateCheckbox(
                    dateCheckbox
                );
            }
        );
    }
);


// =========================================================
// INDIVIDUAL PARENT CHECKBOX
//
// If all parents for that date are selected,
// automatically check the date checkbox.
//
// If only some are selected,
// show indeterminate state.
// =========================================================

parentCheckboxes.forEach(
    function (checkbox) {

        checkbox.addEventListener(
            "change",
            function () {

                const dateValue =
                    checkbox.dataset.date;

                const dateCheckbox =
                    document.querySelector(
                        '.date-checkbox[data-date="' +
                        CSS.escape(
                            dateValue
                        ) +
                        '"]'
                    );

                if (dateCheckbox) {
                    updateDateCheckbox(
                        dateCheckbox
                    );
                }
            }
        );
    }
);


// =========================================================
// NOTICE MODAL
// =========================================================

function showNoticeModal(
    title,
    message
) {
    if (
        !noticeTitle ||
        !noticeMessage ||
        !noticeModal
    ) {
        return;
    }

    noticeTitle.textContent =
        title;

    noticeMessage.textContent =
        message;

    noticeModal.classList.add(
        "show"
    );
}


function closeNoticeModal() {
    if (!noticeModal) {
        return;
    }

    noticeModal.classList.remove(
        "show"
    );
}


// =========================================================
// START DELETE MODE
// =========================================================

if (startDeleteButton) {
    startDeleteButton.addEventListener(
        "click",
        function () {

            body.classList.add(
                "delete-mode"
            );

            showDateSelectors();
        }
    );
}


// =========================================================
// CANCEL DELETE MODE
// =========================================================

if (cancelDeleteButton) {
    cancelDeleteButton.addEventListener(
        "click",
        function () {

            clearSelections();

            hideDateSelectors();

            body.classList.remove(
                "delete-mode"
            );
        }
    );
}


// =========================================================
// DELETE SELECTED
// =========================================================

if (prepareDeleteButton) {
    prepareDeleteButton.addEventListener(
        "click",
        function () {

            const selected =
                selectedCheckboxes();

            if (selected.length === 0) {
                showNoticeModal(
                    "Nothing selected",
                    "Please select at least one parent email."
                );

                return;
            }

            if (confirmDeleteMessage) {
                confirmDeleteMessage.textContent =
                    "Delete " +
                    selected.length +
                    " selected parent email(s)? " +
                    "All replacement emails below them " +
                    "will also be deleted.";
            }

            if (confirmModal) {
                confirmModal.classList.add(
                    "show"
                );
            }
        }
    );
}


// =========================================================
// CLOSE NOTICE
// =========================================================

if (closeNoticeButton) {
    closeNoticeButton.addEventListener(
        "click",
        closeNoticeModal
    );
}


// =========================================================
// CANCEL CONFIRM DELETE
// =========================================================

if (cancelConfirmButton) {
    cancelConfirmButton.addEventListener(
        "click",
        function () {

            if (confirmModal) {
                confirmModal.classList.remove(
                    "show"
                );
            }
        }
    );
}


// =========================================================
// CONFIRM DELETE
// =========================================================

if (confirmDeleteButton) {
    confirmDeleteButton.addEventListener(
        "click",
        function () {

            if (deleteForm) {
                deleteForm.submit();
            }
        }
    );
}


// =========================================================
// CLOSE NOTICE WHEN CLICKING BACKDROP
// =========================================================

if (noticeModal) {
    noticeModal.addEventListener(
        "click",
        function (event) {

            if (
                event.target ===
                noticeModal
            ) {
                closeNoticeModal();
            }
        }
    );
}


// =========================================================
// CLOSE CONFIRM WHEN CLICKING BACKDROP
// =========================================================

if (confirmModal) {
    confirmModal.addEventListener(
        "click",
        function (event) {

            if (
                event.target ===
                confirmModal
            ) {
                confirmModal.classList.remove(
                    "show"
                );
            }
        }
    );
}


// =========================================================
// NOTICE MESSAGES
// =========================================================

const noticeMessages = {
    none_selected: [
        "Nothing selected",
        "Please select at least one parent email."
    ],

    deleted: [
        "Deleted",
        "The selected parent accounts and their replacements were deleted."
    ],

    added: [
        "Emails added",
        "The parent email accounts were added successfully."
    ],

    replacement_added: [
        "Replacement added",
        "The replacement account was attached successfully."
    ],

    email_updated: [
        "Email updated",
        "The email account was updated successfully."
    ]
};


if (
    window.EMAIL_NOTICE &&
    noticeMessages[
        window.EMAIL_NOTICE
    ]
) {
    window.addEventListener(
        "load",
        function () {

            const message =
                noticeMessages[
                    window.EMAIL_NOTICE
                ];

            showNoticeModal(
                message[0],
                message[1]
            );
        }
    );
}


// =========================================================
// COPY EMAIL / PASSWORD
// =========================================================

document.querySelectorAll(
    ".copy-email-button"
).forEach(
    function (button) {

        button.addEventListener(
            "click",
            async function () {

                const copyType =
                    button.dataset.copyType;

                const email =
                    button.dataset.email;

                const password =
                    button.dataset.password;

                const copyText =
                    copyType +
                    "\n\n" +
                    email +
                    "\n" +
                    "password: " +
                    password +
                    "\n\n" +
                    "Guide to login: " +
                    "https://mantapnet.my/instructions" +
                    "\n\n" +
                    "Get code at " +
                    "https://mantapnet.my/get-code";

                try {
                    await navigator
                        .clipboard
                        .writeText(
                            copyText
                        );

                    const originalText =
                        button.textContent;

                    button.textContent =
                        "Copied";

                    setTimeout(
                        function () {
                            button.textContent =
                                originalText;
                        },
                        1200
                    );

                } catch (error) {

                    const textarea =
                        document.createElement(
                            "textarea"
                        );

                    textarea.value =
                        copyText;

                    textarea.style.position =
                        "fixed";

                    textarea.style.opacity =
                        "0";

                    document.body.appendChild(
                        textarea
                    );

                    textarea.select();

                    document.execCommand(
                        "copy"
                    );

                    textarea.remove();

                    const originalText =
                        button.textContent;

                    button.textContent =
                        "Copied";

                    setTimeout(
                        function () {
                            button.textContent =
                                originalText;
                        },
                        1200
                    );
                }
            }
        );
    }
);


// =========================================================
// DATE JUMP NAVIGATION
// =========================================================

const dateSections =
    document.querySelectorAll(
        ".email-date-group"
    );

const dateButtons =
    document.querySelectorAll(
        ".date-jump-button"
    );


if (
    dateSections.length > 0 &&
    dateButtons.length > 0
) {
    const dateObserver =
        new IntersectionObserver(
            function (entries) {

                entries.forEach(
                    function (entry) {

                        if (
                            !entry.isIntersecting
                        ) {
                            return;
                        }

                        dateButtons.forEach(
                            function (button) {
                                button.classList.remove(
                                    "active"
                                );
                            }
                        );

                        const activeButton =
                            document.querySelector(
                                '.date-jump-button[href="#' +
                                entry.target.id +
                                '"]'
                            );

                        if (activeButton) {
                            activeButton
                                .classList
                                .add(
                                    "active"
                                );
                        }
                    }
                );
            },
            {
                rootMargin:
                    "-80px 0px -75% 0px",

                threshold: 0
            }
        );

    dateSections.forEach(
        function (section) {
            dateObserver.observe(
                section
            );
        }
    );
}


// =========================================================
// PAGE FIND BAR
// =========================================================

const pageFindBar =
    document.getElementById(
        "pageFindBar"
    );

const pageFindInput =
    document.getElementById(
        "pageFindInput"
    );

const pageFindCount =
    document.getElementById(
        "pageFindCount"
    );

const pageFindPrevious =
    document.getElementById(
        "pageFindPrevious"
    );

const pageFindNext =
    document.getElementById(
        "pageFindNext"
    );

const pageFindClose =
    document.getElementById(
        "pageFindClose"
    );

const openPageFind =
    document.getElementById(
        "openPageFind"
    );


let pageFindMatches = [];
let pageFindCurrentIndex = -1;


// =========================================================
// GET EMAIL ROWS
// =========================================================

function getEmailRows() {
    return Array.from(
        document.querySelectorAll(
            ".email-row"
        )
    );
}


// =========================================================
// OPEN FIND BAR
// =========================================================

function openFindBar() {
    if (
        !pageFindBar ||
        !pageFindInput
    ) {
        return;
    }

    pageFindBar.hidden = false;

    requestAnimationFrame(
        function () {
            pageFindInput.focus();
            pageFindInput.select();
        }
    );
}


// =========================================================
// CLEAR FIND STATE
// =========================================================

function clearFindState() {
    getEmailRows().forEach(
        function (row) {

            row.classList.remove(
                "find-match",
                "find-current"
            );
        }
    );

    pageFindMatches = [];
    pageFindCurrentIndex = -1;

    if (pageFindCount) {
        pageFindCount.textContent =
            "0 results";
    }
}


// =========================================================
// CLOSE FIND BAR
// =========================================================

function closeFindBar() {
    if (
        !pageFindBar ||
        !pageFindInput
    ) {
        return;
    }

    pageFindBar.hidden = true;

    pageFindInput.value = "";

    clearFindState();
}


// =========================================================
// UPDATE CURRENT FIND MATCH
// =========================================================

function updateCurrentMatch() {

    pageFindMatches.forEach(
        function (row, index) {

            row.classList.toggle(
                "find-current",
                index ===
                    pageFindCurrentIndex
            );
        }
    );

    if (
        pageFindCurrentIndex >= 0 &&
        pageFindMatches[
            pageFindCurrentIndex
        ]
    ) {
        pageFindMatches[
            pageFindCurrentIndex
        ].scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    if (pageFindCount) {
        if (
            pageFindMatches.length === 0
        ) {
            pageFindCount.textContent =
                "0 results";
        } else {
            pageFindCount.textContent =
                (
                    pageFindCurrentIndex +
                    1
                ) +
                " / " +
                pageFindMatches.length;
        }
    }
}


// =========================================================
// RUN PAGE FIND
// =========================================================

function runPageFind() {

    const query =
        pageFindInput
            ? pageFindInput
                .value
                .trim()
                .toLowerCase()
            : "";

    const rows =
        getEmailRows();

    pageFindMatches = [];
    pageFindCurrentIndex = -1;

    rows.forEach(
        function (row) {

            row.classList.remove(
                "find-match",
                "find-current"
            );

            if (!query) {
                return;
            }

            const rowText =
                row.textContent
                    .toLowerCase();

            if (
                rowText.includes(
                    query
                )
            ) {
                row.classList.add(
                    "find-match"
                );

                pageFindMatches.push(
                    row
                );
            }
        }
    );

    if (
        query &&
        pageFindMatches.length > 0
    ) {
        pageFindCurrentIndex = 0;
    }

    updateCurrentMatch();
}


// =========================================================
// NEXT FIND MATCH
// =========================================================

function goToNextMatch() {
    if (
        pageFindMatches.length === 0
    ) {
        return;
    }

    pageFindCurrentIndex =
        (
            pageFindCurrentIndex +
            1
        ) %
        pageFindMatches.length;

    updateCurrentMatch();
}


// =========================================================
// PREVIOUS FIND MATCH
// =========================================================

function goToPreviousMatch() {
    if (
        pageFindMatches.length === 0
    ) {
        return;
    }

    pageFindCurrentIndex =
        (
            pageFindCurrentIndex -
            1 +
            pageFindMatches.length
        ) %
        pageFindMatches.length;

    updateCurrentMatch();
}


// =========================================================
// OPEN FIND BUTTON
// =========================================================

if (openPageFind) {
    openPageFind.addEventListener(
        "click",
        openFindBar
    );
}


// =========================================================
// FIND INPUT
// =========================================================

if (pageFindInput) {

    pageFindInput.addEventListener(
        "input",
        runPageFind
    );

    pageFindInput.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key ===
                "Enter"
            ) {
                event.preventDefault();

                if (event.shiftKey) {
                    goToPreviousMatch();
                } else {
                    goToNextMatch();
                }
            }

            if (
                event.key ===
                "Escape"
            ) {
                closeFindBar();
            }
        }
    );
}


// =========================================================
// NEXT FIND BUTTON
// =========================================================

if (pageFindNext) {
    pageFindNext.addEventListener(
        "click",
        goToNextMatch
    );
}


// =========================================================
// PREVIOUS FIND BUTTON
// =========================================================

if (pageFindPrevious) {
    pageFindPrevious.addEventListener(
        "click",
        goToPreviousMatch
    );
}


// =========================================================
// CLOSE FIND BUTTON
// =========================================================

if (pageFindClose) {
    pageFindClose.addEventListener(
        "click",
        closeFindBar
    );
}


// =========================================================
// CTRL + F / CMD + F
// =========================================================

document.addEventListener(
    "keydown",
    function (event) {

        const isFindShortcut =
            (
                event.ctrlKey ||
                event.metaKey
            ) &&
            event.key
                .toLowerCase() ===
                "f";

        if (!isFindShortcut) {
            return;
        }

        event.preventDefault();

        openFindBar();
    }
);


// =========================================================
// INITIAL STATE
//
// Date checkboxes must stay hidden until Delete is clicked.
// =========================================================

hideDateSelectors();

let amountDigits = "";

const amountDisplay = document.getElementById("amountDisplay");
const amountValue = document.getElementById("amountValue");

function updateAmountField() {
    let cents = parseInt(amountDigits || "0", 10);

    let amount = cents / 100;

    amountDisplay.value =
        "RM " +
        amount.toLocaleString("en-MY", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });

    amountValue.value = amount.toFixed(2);
}

amountDisplay.addEventListener("keydown", function (event) {

    // Allow navigation keys
    if (
        event.key === "Tab" ||
        event.key === "ArrowLeft" ||
        event.key === "ArrowRight" ||
        event.key === "Home" ||
        event.key === "End"
    ) {
        return;
    }

    event.preventDefault();

    // Numbers
    if (/^[0-9]$/.test(event.key)) {

        // Prevent ridiculous amounts
        if (amountDigits.length < 12) {
            amountDigits += event.key;
        }

        updateAmountField();
        return;
    }

    // Backspace removes the last digit
    if (event.key === "Backspace") {

        amountDigits = amountDigits.slice(0, -1);

        updateAmountField();
        return;
    }

    // Delete / Escape clears amount
    if (
        event.key === "Delete" ||
        event.key === "Escape"
    ) {

        amountDigits = "";

        updateAmountField();
    }
});

amountDisplay.addEventListener("focus", function () {
    this.select();
});

amountDisplay.addEventListener("paste", function (event) {

    event.preventDefault();

    let pasted = (
        event.clipboardData ||
        window.clipboardData
    ).getData("text");

    // Keep only numbers
    pasted = pasted.replace(/\D/g, "");

    if (!pasted) {
        return;
    }

    amountDigits = pasted.slice(0, 12);

    updateAmountField();
});

updateAmountField();
