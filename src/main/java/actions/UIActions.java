package actions;
 
import org.openqa.selenium.By;
import org.openqa.selenium.By.ByXPath;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait; 
import static actions.BrowserActions.driver;


public class UIActions {
		//variables
	  //  private final WebDriver driverhomepage   ;
	    // Constructor method
	   /*   public UIActions (WebDriver driver1) {

	       this.driverhomepage = driver1 ;
	    }  */ 
	     
	       
	  
	   public void navigateToAnyPAge(String pageUrl , By elementPath ) {  
		  WebElement element  ;    // loop to ensure navigation is done .
		  do {
			      
				driver.navigate().to(pageUrl);     // instead of creating driver for each page make one static  driver 
			     element = (new WebDriverWait(driver, 5))  //  in Browseraction class and import it in every class .
				.until(ExpectedConditions.presenceOfElementLocated(elementPath));
		        
			}while( element ==null); 
		    
		   //  driverhomepage.navigate().to("https://www.levelset.com/");
	  } 
 
	   
	   public String check_navigaton_tothe_rigthPage(By elementPath ) {
		 
		   String checkhomepage  =  driver.findElement(elementPath).getText() ;
	        return checkhomepage ;
		        
	   } 
	   public boolean checkclickable_Button(By elementPath) {
		   
	    	 //     create wait object to check button is clickable .
			WebDriverWait wait = new WebDriverWait(driver, 15);
		     WebElement element =wait.until(ExpectedConditions.elementToBeClickable( elementPath));  
		    //    System.out.println("------------------"+element); 
		     // to confim that elementToBeClickable return webelement which mean button is clickable
			          if(element!=null) { 
			        	  driver.findElement( elementPath).click();
			        	  return true ;  
			          }else
				     	return false; 
			          
	    }
	   
	   public void click (By elementpath ) { 
		   WebDriverWait wait = new WebDriverWait(driver, 15); 
		 WebElement element =wait.until(ExpectedConditions.elementToBeClickable( elementpath));  
		  if(element!=null) 
		  {
		     driver.findElement(elementpath).click();
		   
		  }
		  
	   }
	   public String get_text (String locator ,String type ) {
	        
		       if (  type == "Xpath"  )
		       { 
		         By elementpath = By.xpath(locator);
		         
		     String text = driver.findElement(elementpath).getText();
		                 return text;
		       }
			    return null;   
		         
	   }

   public void search_forDocumentInSearchBar( String documentname ) { 
	
	     By document_search =  By.name("document_search");
	      
	     // apply waiting for verifying the visibility of element .
	     WebDriverWait wait = new WebDriverWait(driver, 15) ;
	   WebElement element=  wait.until(ExpectedConditions.presenceOfElementLocated(document_search)) ;
	         if ( element!= null) {
	        	 
	     driver.findElement((By) document_search).sendKeys(documentname); 
	    
	         } 
	         
	   
   }

	   
}
