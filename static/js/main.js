// Home hero slider: rotates the active hero background image every few seconds.

const slides =
document.querySelectorAll(".hero-slide");

let currentSlide = 0;

function changeSlide(){

    if(slides.length === 0) return;

    slides[currentSlide]
    .classList.remove("active");

    currentSlide =
    (currentSlide + 1)
    % slides.length;

    slides[currentSlide]
    .classList.add("active");

}

setInterval(changeSlide,4000);


// Delete confirmation: shows a SweetAlert prompt, then submits a POST form with CSRF.

function deleteListing(id){

    Swal.fire({

        title:'Delete Listing?',

        text:'This listing will be removed.',

        icon:'warning',

        showCancelButton:true,

        confirmButtonColor:'#ef4444',

        confirmButtonText:'Delete'

    }).then((result)=>{

        if(result.isConfirmed){

            const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
            const form = document.createElement("form");
            form.method = "POST";
            form.action = "/delete/" + id;

            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "_csrf_token";
            input.value = token;

            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();

        }

    });

}

// Legacy category filter: fetches category results and replaces the listing container.
async function filterCategory(name){

    const res = await fetch(`/api/category/${name}`);
    const data = await res.json();

    const container = document.getElementById("listing-container");

    container.innerHTML = "";

    const listingImageSrc = (image) => {
        if (!image) return "/static/images/aesthetic-room-decor.jpg";
        if (image.startsWith("http://") || image.startsWith("https://")) return image;
        return `/static/images/${image}`;
    };

    data.forEach(item => {

        container.innerHTML += `
        <div class="card">

            <img src="${listingImageSrc(item.image)}" onerror="this.onerror=null; this.src='/static/images/aesthetic-room-decor.jpg';">

            <div class="content">

                <h3>${item.title}</h3>

                <div class="price">₹${item.price}</div>

                <div class="location">📍 ${item.location}</div>

                <a class="map"
                   target="_blank"
                   href="https://www.google.com/maps?q=${item.latitude},${item.longitude}">
                   View on map →
                </a>

            </div>

        </div>
        `;
    });
}

// Listing image slider: moves between images inside one listing card.
function changeSlide(button,direction){

    const imageBox =
    button.closest(".images");

    const slides =
    imageBox.querySelectorAll(".slide");

    let activeIndex = 0;

    slides.forEach((slide,index)=>{

        if(slide.classList.contains("active-slide")){

            activeIndex = index;

        }

    });

    slides[activeIndex]
    .classList.remove("active-slide");

    activeIndex =
    (activeIndex + direction + slides.length)
    % slides.length;

    slides[activeIndex]
    .classList.add("active-slide");

}
